"""Decode hex Mode S messages and maintain per-ICAO aircraft state."""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Tuple

import pyModeS as pms
from pyModeS.errors import InvalidHexError, InvalidLengthError

from aircraftx.config import (
    MAX_ADSB_TRACKS,
    MAX_ALTITUDE_FT,
    MAX_GROUNDSPEED_KT,
    MAX_MODE_S_TRACKS,
    MIN_ALTITUDE_FT,
    PREFERRED_DF,
    TrackerSettings,
)
from aircraftx.models.aircraft import Aircraft


class AircraftTracker:
    def __init__(
        self,
        lat_ref: Optional[float] = None,
        lon_ref: Optional[float] = None,
        settings: Optional[TrackerSettings] = None,
    ) -> None:
        surface_ref: Optional[Tuple[float, float]] = None
        if lat_ref is not None and lon_ref is not None:
            surface_ref = (lat_ref, lon_ref)
        self.lat_ref = lat_ref
        self.lon_ref = lon_ref
        self.settings = settings or TrackerSettings.outdoor()
        self._pipe = pms.PipeDecoder(surface_ref=surface_ref)
        self.aircraft: Dict[str, Aircraft] = {}
        self.total_messages = 0
        self.total_crc_ok = 0
        self.df17_messages = 0
        self.mode_s_messages = 0
        self.rejected_sanity = 0

    def purge_stale(self, now: float) -> None:
        stale = [
            icao
            for icao, ac in self.aircraft.items()
            if not ac.is_confirmed(now, self.settings.min_confirm_hits)
            and now - ac.last_seen > self.settings.stale_unconfirmed_sec
        ]
        for icao in stale:
            del self.aircraft[icao]
        self._enforce_track_caps()

    def _enforce_track_caps(self) -> None:
        self._cap_tracks(lambda ac: ac.df17_count == 0, MAX_MODE_S_TRACKS)
        self._cap_tracks(lambda ac: ac.df17_count > 0, MAX_ADSB_TRACKS)

    def _cap_tracks(self, include: Callable[[Aircraft], bool], limit: int) -> None:
        bucket = [(icao, ac) for icao, ac in self.aircraft.items() if include(ac)]
        if len(bucket) <= limit:
            return
        bucket.sort(key=lambda item: item[1].last_seen)
        for icao, _ in bucket[: len(bucket) - limit]:
            del self.aircraft[icao]

    def confirmed_aircraft(self, now: float) -> List[Aircraft]:
        return [
            ac
            for ac in self.aircraft.values()
            if ac.is_confirmed(now, self.settings.min_confirm_hits)
        ]

    def ingest(self, hex_msg: str, now: Optional[float] = None) -> Optional[Aircraft]:
        now = now or time.time()
        try:
            if not pms.Message(hex_msg).crc_valid:
                return None
        except (InvalidHexError, InvalidLengthError):
            return None

        decoded = self._pipe.decode(hex_msg, timestamp=now)
        df = decoded.get("df")
        if not self._sanity_ok(decoded):
            self.rejected_sanity += 1
            return None

        self.total_crc_ok += 1
        self._apply_cpr_reference(hex_msg, decoded)

        icao = decoded.get("icao")
        if not icao:
            return None

        ac = self.aircraft.get(icao)
        if ac is None:
            ac = Aircraft(icao=icao, first_seen=now)
            self.aircraft[icao] = ac

        self._update_aircraft(ac, decoded, hex_msg, now)
        self._enforce_track_caps()
        return ac

    def _apply_cpr_reference(self, hex_msg: str, decoded: dict) -> None:
        if decoded.get("latitude") is not None:
            return
        if self.lat_ref is None or self.lon_ref is None:
            return
        tc = decoded.get("typecode")
        if tc is None or not 9 <= tc <= 18:
            return
        ref = pms.decode(hex_msg, reference=(self.lat_ref, self.lon_ref))
        if ref.get("latitude") is not None:
            decoded["latitude"] = ref["latitude"]
            decoded["longitude"] = ref["longitude"]

    def _update_aircraft(
        self, ac: Aircraft, decoded: dict, hex_msg: str, now: float
    ) -> None:
        ac.message_count += 1
        ac.last_seen = now
        ac.hit_times.append(now)
        ac.seen_hex.add(hex_msg)
        ac.last_df = decoded.get("df")
        ac.last_tc = decoded.get("typecode")
        if ac.last_df in PREFERRED_DF:
            ac.df17_count += 1
            ac.last_adsb_df = ac.last_df
            ac.last_adsb_tc = ac.last_tc
            self.df17_messages += 1
        else:
            self.mode_s_messages += 1

        if decoded.get("callsign"):
            ac.callsign = str(decoded["callsign"]).strip()
        if decoded.get("altitude") is not None:
            ac.altitude_ft = int(decoded["altitude"])
        if decoded.get("groundspeed") is not None:
            ac.speed_kts = float(decoded["groundspeed"])
        track = decoded.get("track") or decoded.get("true_track")
        if track is not None:
            ac.heading_deg = float(track)
        if decoded.get("vertical_rate") is not None:
            ac.vertical_rate_fpm = int(decoded["vertical_rate"])
        if decoded.get("latitude") is not None:
            ac.latitude = float(decoded["latitude"])
        if decoded.get("longitude") is not None:
            ac.longitude = float(decoded["longitude"])
        if decoded.get("squawk"):
            ac.squawk = str(decoded["squawk"])
        if decoded.get("category") is not None:
            ac.category = str(decoded.get("wake_vortex") or decoded["category"])
        if decoded.get("bds"):
            ac.bds = str(decoded["bds"])

    @staticmethod
    def _sanity_ok(decoded: dict) -> bool:
        alt = decoded.get("altitude")
        if alt is not None and not (MIN_ALTITUDE_FT <= int(alt) <= MAX_ALTITUDE_FT):
            return False
        gs = decoded.get("groundspeed")
        if gs is not None and not (0 <= float(gs) <= MAX_GROUNDSPEED_KT):
            return False
        return True

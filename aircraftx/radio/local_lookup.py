"""Fetch nearby airport voice frequencies from OurAirports open data."""

from __future__ import annotations

import csv
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from aircraftx.config import AIRBAND_MAX_MHZ, AIRBAND_MIN_MHZ
from aircraftx.radio.channels import AirbandChannel

_OURAIRPORTS_BASE = "https://davidmegginson.github.io/ourairports-data"
_CACHE_DIR = Path.home() / ".cache" / "aircraftx" / "ourairports"
_CACHE_MAX_AGE_SEC = 7 * 24 * 3600

_AIRPORT_TYPES = frozenset({"large_airport", "medium_airport", "small_airport"})
_VOICE_FREQ_TYPES = frozenset(
    {
        "ATIS",
        "TWR",
        "GND",
        "APP",
        "DEP",
        "CTAF",
        "UNICOM",
        "MULTICOM",
        "RAMP",
        "CLEARANCE",
        "CLD",
        "FSS",
        "AWOS",
        "ASOS",
        "RDO",
    }
)
# OurAirports omits or mislabels some published freqs; fill gaps for busy airports.
_REGIONAL_SUPPLEMENTS: Dict[str, Tuple[Tuple[str, str, float, str], ...]] = {
    "KEWR": (
        ("ATIS", "ATIS Arr/Dep", 134.825, "Newark D-ATIS loop"),
        ("DEP", "Departure", 119.2, "New York Departure"),
        ("APP", "Approach", 128.55, "New York Approach Yardley"),
    ),
    "KJFK": (
        ("ATIS", "ATIS", 128.725, "Kennedy ATIS loop"),
        ("APP", "Approach CAMRN", 128.125, "New York Approach CAMRN"),
        ("TWR", "Tower Class B", 125.25, "Kennedy Tower Class B"),
    ),
    "KLGA": (("ATIS", "ATIS Dep", 125.95, "LaGuardia ATIS"),),
}

_TYPE_ORDER = {
    "ATIS": 0,
    "AWOS": 1,
    "ASOS": 2,
    "TWR": 3,
    "GND": 4,
    "CLEARANCE": 5,
    "CLD": 5,
    "DEP": 6,
    "APP": 7,
    "CTAF": 8,
    "UNICOM": 9,
    "MULTICOM": 10,
    "RAMP": 11,
    "FSS": 12,
    "RDO": 13,
}


@dataclass(frozen=True)
class _Airport:
    ident: str
    name: str
    latitude: float
    longitude: float
    airport_type: str
    distance_km: float


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "AircraftX/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dest.write_bytes(resp.read())


def _cache_path(name: str) -> Path:
    return _CACHE_DIR / name


def _ensure_dataset(filename: str) -> Path:
    path = _cache_path(filename)
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < _CACHE_MAX_AGE_SEC:
            return path
    url = f"{_OURAIRPORTS_BASE}/{filename}"
    try:
        _download(url, path)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if path.exists():
            return path
        raise RuntimeError(f"Unable to download OurAirports data ({url})") from exc
    return path


def _read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def _nearest_airports(
    lat: float,
    lon: float,
    *,
    radius_km: float,
    max_airports: int,
    airports_csv: Path,
    frequencies_csv: Path,
) -> List[_Airport]:
    freqs_by_ident: Dict[str, List[dict[str, str]]] = {}
    for row in _read_csv(frequencies_csv):
        ident = (row.get("airport_ident") or "").strip().upper()
        if not ident:
            continue
        freq_type = (row.get("type") or "").strip().upper()
        if freq_type not in _VOICE_FREQ_TYPES:
            continue
        try:
            float(row.get("frequency_mhz") or "")
        except ValueError:
            continue
        freqs_by_ident.setdefault(ident, []).append(row)

    lat_delta = radius_km / 111.0
    cos_lat = max(0.2, abs(math.cos(math.radians(lat))))
    lon_delta = radius_km / (111.0 * cos_lat)

    candidates: List[_Airport] = []
    for row in _read_csv(airports_csv):
        ident = (row.get("ident") or "").strip().upper()
        if not ident or ident not in freqs_by_ident:
            continue
        airport_type = (row.get("type") or "").strip()
        if airport_type not in _AIRPORT_TYPES:
            continue
        try:
            alat = float(row["latitude_deg"])
            alon = float(row["longitude_deg"])
        except (KeyError, ValueError):
            continue
        if abs(alat - lat) > lat_delta or abs(alon - lon) > lon_delta:
            continue
        dist = _haversine_km(lat, lon, alat, alon)
        if dist > radius_km:
            continue
        name = (row.get("name") or ident).strip()
        candidates.append(
            _Airport(
                ident=ident,
                name=name,
                latitude=alat,
                longitude=alon,
                airport_type=airport_type,
                distance_km=dist,
            )
        )

    candidates.sort(key=lambda a: (a.distance_km, a.ident))
    return candidates[:max_airports]


def _freq_sort_key(row: dict[str, str]) -> Tuple[int, float]:
    freq_type = (row.get("type") or "").strip().upper()
    try:
        mhz = float(row.get("frequency_mhz") or "")
    except ValueError:
        mhz = 0.0
    return (_TYPE_ORDER.get(freq_type, 99), mhz)


def lookup_local_channels(
    lat: float,
    lon: float,
    *,
    radius_km: float = 80.0,
    max_airports: int = 8,
) -> List[AirbandChannel]:
    """Return voice channels for airports near *lat*/*lon* from OurAirports."""
    airports_csv = _ensure_dataset("airports.csv")
    frequencies_csv = _ensure_dataset("airport-frequencies.csv")
    airports = _nearest_airports(
        lat,
        lon,
        radius_km=radius_km,
        max_airports=max_airports,
        airports_csv=airports_csv,
        frequencies_csv=frequencies_csv,
    )

    channels: List[AirbandChannel] = []
    seen_hz: set[int] = set()

    for airport in airports:
        rows = sorted(
            _read_freqs_for(airport.ident, frequencies_csv), key=_freq_sort_key
        )
        for row in rows:
            freq_type = (row.get("type") or "").strip().upper()
            if freq_type not in _VOICE_FREQ_TYPES:
                continue
            try:
                mhz = float(row.get("frequency_mhz") or "")
            except ValueError:
                continue
            if mhz < AIRBAND_MIN_MHZ or mhz > AIRBAND_MAX_MHZ:
                continue
            _append_channel(
                channels,
                seen_hz,
                ident=airport.ident,
                airport_name=airport.name,
                distance_km=airport.distance_km,
                freq_type=freq_type,
                mhz=mhz,
                label_detail=(row.get("description") or "").strip(),
            )

        for freq_type, label, mhz, note in _REGIONAL_SUPPLEMENTS.get(airport.ident, ()):
            if mhz < AIRBAND_MIN_MHZ or mhz > AIRBAND_MAX_MHZ:
                continue
            _append_channel(
                channels,
                seen_hz,
                ident=airport.ident,
                airport_name=airport.name,
                distance_km=airport.distance_km,
                freq_type=freq_type,
                mhz=mhz,
                label_detail=label,
                description_note=note,
            )
    return channels


def _append_channel(
    channels: List[AirbandChannel],
    seen_hz: set[int],
    *,
    ident: str,
    airport_name: str,
    distance_km: float,
    freq_type: str,
    mhz: float,
    label_detail: str,
    description_note: str = "",
) -> None:
    freq_hz = int(round(mhz * 1_000_000))
    if freq_hz in seen_hz:
        return
    seen_hz.add(freq_hz)

    label = freq_type.title()
    if label_detail and label_detail.upper() not in {freq_type, "CLD"}:
        label = f"{label} — {label_detail}"

    dist = f"{distance_km:.0f} km"
    desc = (
        airport_name if not description_note else f"{airport_name} — {description_note}"
    )
    channels.append(
        AirbandChannel(
            channel_id=f"{ident}:{mhz:.3f}",
            name=f"{label} {ident}",
            freq_hz=freq_hz,
            description=f"{desc} ({dist})",
        )
    )


def _read_freqs_for(ident: str, frequencies_csv: Path) -> List[dict[str, str]]:
    ident = ident.upper()
    rows: List[dict[str, str]] = []
    for row in _read_csv(frequencies_csv):
        if (row.get("airport_ident") or "").strip().upper() == ident:
            rows.append(row)
    return rows

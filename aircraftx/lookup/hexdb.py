"""hexdb.io REST client for ICAO, aircraft, and route lookups."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Optional

_HEXDB_BASE = "https://hexdb.io/api/v1"
_HEXDB_SITE = "https://hexdb.io"
_USER_AGENT = "AircraftX/1.0 (ADS-B receiver; +https://github.com/ericbenner/aircraftx)"
_TIMEOUT_SEC = 6.0
_MIN_REQUEST_INTERVAL_SEC = 0.35
_MAX_RETRIES = 3

_rate_lock = threading.Lock()
_last_request = 0.0


class LookupOutcome(str, Enum):
    OK = "ok"
    NOT_FOUND = "not_found"
    TRANSIENT = "transient"


@dataclass(frozen=True)
class HexdbAircraft:
    registration: str
    manufacturer: str
    aircraft_type: str
    icao_type_code: str
    operator: str
    owner: str


@dataclass(frozen=True)
class HexdbRoute:
    flight: str
    route: str
    departure: str
    destination: str


@dataclass(frozen=True)
class AircraftLookupResult:
    outcome: LookupOutcome
    aircraft: Optional[HexdbAircraft] = None


def _pace_requests() -> None:
    global _last_request
    with _rate_lock:
        wait = _MIN_REQUEST_INTERVAL_SEC - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _request(url: str) -> tuple[Optional[bytes], Optional[int], Optional[str]]:
    """Return (body, http_status, error). http_status None means transport failure."""
    _pace_requests()
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            return resp.read(), resp.status, None
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001
            body = None
        return body, exc.code, str(exc.reason)
    except (urllib.error.URLError, TimeoutError) as exc:
        return None, None, str(exc)


def _transient_status(code: Optional[int]) -> bool:
    if code is None:
        return True
    return code in (403, 408, 429, 500, 502, 503, 504)


def _get_json(path: str) -> tuple[Optional[dict], LookupOutcome]:
    url = f"{_HEXDB_BASE}{path}"
    last_outcome = LookupOutcome.TRANSIENT
    for attempt in range(_MAX_RETRIES):
        body, status, _err = _request(url)
        if status == 404:
            return None, LookupOutcome.NOT_FOUND
        if body is None or _transient_status(status):
            last_outcome = LookupOutcome.TRANSIENT
            if attempt + 1 < _MAX_RETRIES:
                time.sleep(0.4 * (2**attempt))
            continue
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            last_outcome = LookupOutcome.TRANSIENT
            if attempt + 1 < _MAX_RETRIES:
                time.sleep(0.4 * (2**attempt))
            continue
        if not isinstance(data, dict):
            return None, LookupOutcome.NOT_FOUND
        if data.get("status") == "404" or data.get("error"):
            return None, LookupOutcome.NOT_FOUND
        return data, LookupOutcome.OK
    return None, last_outcome


def _get_text(path: str) -> tuple[str, LookupOutcome]:
    url = f"{_HEXDB_SITE}{path}"
    body, status, _err = _request(url)
    if status == 404:
        return "", LookupOutcome.NOT_FOUND
    if body is None or _transient_status(status):
        return "", LookupOutcome.TRANSIENT
    text = body.decode("utf-8", errors="replace").strip()
    if not text or text.lower() in {"n/a", "na", "none", "unknown"}:
        return "", LookupOutcome.NOT_FOUND
    return text, LookupOutcome.OK


def _parse_aircraft_json(data: dict) -> Optional[HexdbAircraft]:
    registration = str(data.get("Registration") or "").strip()
    if not registration:
        return None
    return HexdbAircraft(
        registration=registration,
        manufacturer=str(data.get("Manufacturer") or "").strip(),
        aircraft_type=str(data.get("Type") or "").strip(),
        icao_type_code=str(data.get("ICAOTypeCode") or "").strip(),
        operator=str(data.get("OperatorFlagCode") or "").strip(),
        owner=str(data.get("RegisteredOwners") or "").strip(),
    )


def _lookup_aircraft_legacy(hex_id: str) -> AircraftLookupResult:
    registration, reg_outcome = _get_text(f"/hex-reg?hex={hex_id}")
    if reg_outcome == LookupOutcome.TRANSIENT:
        return AircraftLookupResult(outcome=LookupOutcome.TRANSIENT)
    if reg_outcome == LookupOutcome.NOT_FOUND or not registration:
        return AircraftLookupResult(outcome=LookupOutcome.NOT_FOUND)

    aircraft_type, _ = _get_text(f"/hex-type?hex={hex_id}")
    operator, _ = _get_text(f"/hex-airline?hex={hex_id}")
    return AircraftLookupResult(
        outcome=LookupOutcome.OK,
        aircraft=HexdbAircraft(
            registration=registration,
            manufacturer="",
            aircraft_type=aircraft_type,
            icao_type_code="",
            operator=operator,
            owner="",
        ),
    )


def lookup_aircraft_by_hex(icao: str) -> AircraftLookupResult:
    """ICAO hex → registration and aircraft details."""
    hex_id = icao.strip().upper()
    if not hex_id or len(hex_id) != 6:
        return AircraftLookupResult(outcome=LookupOutcome.NOT_FOUND)

    data, outcome = _get_json(f"/aircraft/{hex_id}")
    if outcome == LookupOutcome.OK and data is not None:
        aircraft = _parse_aircraft_json(data)
        if aircraft is not None:
            return AircraftLookupResult(outcome=LookupOutcome.OK, aircraft=aircraft)
        return AircraftLookupResult(outcome=LookupOutcome.NOT_FOUND)

    if outcome == LookupOutcome.NOT_FOUND:
        return _lookup_aircraft_legacy(hex_id)

    legacy = _lookup_aircraft_legacy(hex_id)
    if legacy.outcome == LookupOutcome.OK:
        return legacy
    return AircraftLookupResult(outcome=LookupOutcome.TRANSIENT)


def lookup_route_by_callsign(callsign: str) -> Optional[HexdbRoute]:
    """Flight callsign → departure and destination airports."""
    flight = callsign.strip().upper()
    if not flight:
        return None
    encoded = urllib.parse.quote(flight, safe="")
    data, outcome = _get_json(f"/route/icao/{encoded}")
    if outcome != LookupOutcome.OK or not data:
        return None
    route = str(data.get("route") or "").strip()
    departure, destination = _split_route(route)
    return HexdbRoute(
        flight=str(data.get("flight") or flight).strip(),
        route=route,
        departure=departure,
        destination=destination,
    )


def _split_route(route: str) -> tuple[str, str]:
    if not route:
        return "", ""
    for sep in ("-", "–", "—", ">"):
        if sep in route:
            parts = route.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return route.strip(), ""


def lookup_airport_coords(airport_code: str) -> Optional[tuple[float, float]]:
    """ICAO/IATA airport code → (latitude, longitude)."""
    code = airport_code.strip().upper()
    if len(code) < 3:
        return None
    path = f"/airport/icao/{code}" if len(code) == 4 else f"/airport/iata/{code}"
    data, outcome = _get_json(path)
    if outcome != LookupOutcome.OK or not data:
        return None
    try:
        lat = float(data["latitude"])
        lon = float(data["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    return lat, lon

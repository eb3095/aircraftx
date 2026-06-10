from __future__ import annotations

import time
from unittest.mock import patch

from aircraftx.lookup.hexdb import (
    AircraftLookupResult,
    HexdbAircraft,
    HexdbRoute,
    LookupOutcome,
)
from aircraftx.lookup.models import AircraftEnrichment
from aircraftx.lookup.service import AircraftLookupService


def test_enqueue_dedupes_active_lookups():
    service = AircraftLookupService()
    try:
        service.sync_active_icaos({"ABC123"})
        service.enqueue_aircraft("ABC123")
        service.enqueue_aircraft("ABC123")
        assert service.pending_count() == 1
    finally:
        service.shutdown()


def test_cleanup_drops_stale_cache_entries():
    service = AircraftLookupService()
    try:
        with service._lock:
            service._cache["STALE1"] = AircraftEnrichment(icao="STALE1", status="ready")
            service._cache["KEEP01"] = AircraftEnrichment(icao="KEEP01", status="ready")
            service._active_icaos = {"KEEP01"}
        service._last_cleanup = 0.0
        service._maybe_cleanup()
        with service._lock:
            assert "STALE1" not in service._cache
            assert "KEEP01" in service._cache
    finally:
        service.shutdown()


def test_fetch_aircraft_without_callsign():
    service = AircraftLookupService()
    aircraft = HexdbAircraft(
        registration="G-EZBZ",
        manufacturer="Airbus",
        aircraft_type="A319 111",
        icao_type_code="A319",
        operator="EZY",
        owner="easyJet UK",
    )
    result = AircraftLookupResult(outcome=LookupOutcome.OK, aircraft=aircraft)
    with patch("aircraftx.lookup.service.hexdb.lookup_aircraft_by_hex", return_value=result):
        fetched = service._fetch_aircraft("4010EE")
    assert fetched.status == "ready"
    assert fetched.registration == "G-EZBZ"
    assert fetched.route == ""
    service.shutdown()


def test_fetch_transient_requeues():
    service = AircraftLookupService()
    transient = AircraftLookupResult(outcome=LookupOutcome.TRANSIENT)
    with patch("aircraftx.lookup.service.hexdb.lookup_aircraft_by_hex", return_value=transient):
        fetched = service._fetch_aircraft("4010EE")
    assert fetched.status == "queued"
    service.shutdown()


def test_fetch_not_found_message():
    service = AircraftLookupService()
    missing = AircraftLookupResult(outcome=LookupOutcome.NOT_FOUND)
    with patch("aircraftx.lookup.service.hexdb.lookup_aircraft_by_hex", return_value=missing):
        fetched = service._fetch_aircraft("4840D6")
    assert fetched.status == "error"
    assert fetched.error == "Not in lookup database"
    service.shutdown()


def test_sync_active_icaos_normalizes_case():
    service = AircraftLookupService()
    try:
        service.sync_active_icaos({"abc123"})
        with service._lock:
            assert service._active_icaos == {"ABC123"}
    finally:
        service.shutdown()


def test_stale_loading_can_retry():
    service = AircraftLookupService()
    try:
        service.sync_active_icaos({"ABC123"})
        with service._lock:
            service._cache["ABC123"] = AircraftEnrichment(
                icao="ABC123",
                status="loading",
                updated_at=time.time() - 120,
            )
        service.enqueue_aircraft("abc123")
        assert service.pending_count() >= 1
    finally:
        service.shutdown()


def test_route_fetched_once_per_callsign():
    service = AircraftLookupService()
    try:
        service.sync_active_icaos({"ABC123"})
        with service._lock:
            service._cache["ABC123"] = AircraftEnrichment(
                icao="ABC123",
                status="ready",
                registration="N12345",
                manufacturer="Boeing",
            )
        route = HexdbRoute(
            flight="UAL100",
            route="KJFK-KLAX",
            departure="KJFK",
            destination="KLAX",
        )
        with patch(
            "aircraftx.lookup.service.hexdb.lookup_route_by_callsign",
            return_value=route,
        ) as route_mock:
            service.maybe_route("ABC123", "UAL100")
            service.maybe_route("ABC123", "UAL100")
            service.maybe_route("ABC123", "UAL100")
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                entry = service.get("ABC123")
                if entry and entry.route:
                    break
                time.sleep(0.05)
        assert route_mock.call_count == 1
        entry = service.get("ABC123")
        assert entry is not None
        assert entry.route == "KJFK-KLAX"
        assert entry.status == "ready"
    finally:
        service.shutdown()


def test_worker_updates_cache_without_callsign():
    service = AircraftLookupService()
    try:
        service.sync_active_icaos({"4010EE"})
        aircraft = HexdbAircraft(
            registration="G-EZBZ",
            manufacturer="Airbus",
            aircraft_type="A319 111",
            icao_type_code="A319",
            operator="EZY",
            owner="easyJet UK",
        )
        ok = AircraftLookupResult(outcome=LookupOutcome.OK, aircraft=aircraft)
        with patch("aircraftx.lookup.service.hexdb.lookup_aircraft_by_hex", return_value=ok):
            service.enqueue_aircraft("4010ee")
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                entry = service.get("4010EE")
                if entry and entry.status == "ready":
                    break
                time.sleep(0.05)
            entry = service.get("4010ee")
        assert entry is not None
        assert entry.status == "ready"
        assert entry.registration == "G-EZBZ"
    finally:
        service.shutdown()


def test_route_after_aircraft_when_callsign_early():
    service = AircraftLookupService()
    try:
        service.sync_active_icaos({"ABC123"})
        aircraft = HexdbAircraft(
            registration="N12345",
            manufacturer="Boeing",
            aircraft_type="737",
            icao_type_code="B738",
            operator="UAL",
            owner="United",
        )
        route = HexdbRoute(
            flight="UAL100",
            route="KJFK-KLAX",
            departure="KJFK",
            destination="KLAX",
        )
        ok = AircraftLookupResult(outcome=LookupOutcome.OK, aircraft=aircraft)
        with (
            patch("aircraftx.lookup.service.hexdb.lookup_aircraft_by_hex", return_value=ok),
            patch(
                "aircraftx.lookup.service.hexdb.lookup_route_by_callsign",
                return_value=route,
            ),
        ):
            service.maybe_route("ABC123", "UAL100")
            service.enqueue_aircraft("ABC123")
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                entry = service.get("ABC123")
                if entry and entry.status == "ready" and entry.route:
                    break
                time.sleep(0.05)
        entry = service.get("ABC123")
        assert entry is not None
        assert entry.registration == "N12345"
        assert entry.route == "KJFK-KLAX"
    finally:
        service.shutdown()

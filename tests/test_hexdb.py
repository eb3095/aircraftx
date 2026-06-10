from __future__ import annotations

from unittest.mock import patch

from aircraftx.lookup.hexdb import (
    AircraftLookupResult,
    HexdbAircraft,
    LookupOutcome,
    lookup_aircraft_by_hex,
)


def test_lookup_accepts_six_char_hex():
    aircraft = HexdbAircraft(
        registration="N628TS",
        manufacturer="Gulfstream",
        aircraft_type="G650 ER",
        icao_type_code="G650",
        operator="G650",
        owner="Falcon Landing LLC",
    )
    with patch(
        "aircraftx.lookup.hexdb._get_json",
        return_value=({"Registration": "N628TS"}, LookupOutcome.OK),
    ):
        with patch("aircraftx.lookup.hexdb._parse_aircraft_json", return_value=aircraft):
            result = lookup_aircraft_by_hex("A835AF")
    assert result.outcome == LookupOutcome.OK
    assert result.aircraft is not None
    assert result.aircraft.registration == "N628TS"


def test_invalid_hex_length_is_not_found():
    result = lookup_aircraft_by_hex("ABC")
    assert result.outcome == LookupOutcome.NOT_FOUND


def test_rest_failure_falls_back_to_legacy():
    aircraft_type = "G650 ER"
    with (
        patch(
            "aircraftx.lookup.hexdb._get_json",
            return_value=(None, LookupOutcome.TRANSIENT),
        ),
        patch(
            "aircraftx.lookup.hexdb._get_text",
            side_effect=[
                ("N628TS", LookupOutcome.OK),
                (aircraft_type, LookupOutcome.OK),
                ("G650", LookupOutcome.OK),
            ],
        ),
    ):
        result = lookup_aircraft_by_hex("A835AF")
    assert result.outcome == LookupOutcome.OK
    assert result.aircraft is not None
    assert result.aircraft.registration == "N628TS"
    assert result.aircraft.aircraft_type == aircraft_type

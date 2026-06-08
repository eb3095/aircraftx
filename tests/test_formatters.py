from __future__ import annotations

from aircraftx.models.aircraft import Aircraft
from aircraftx.ui.formatters import (
    fmt_altitude_ft,
    fmt_optional,
    fmt_speed_kt,
    message_summary,
)


def test_fmt_optional_missing():
    assert fmt_optional(None) == "—"


def test_fmt_optional_float():
    assert fmt_optional(123.456, "°") == "123.5°"


def test_fmt_altitude_and_speed_units():
    assert fmt_altitude_ft(35000) == "35,000 ft"
    assert fmt_altitude_ft(None) == "—"
    assert fmt_speed_kt(450) == "450 kt"
    assert fmt_speed_kt(450.5) == "450.5 kt"
    assert fmt_speed_kt(None) == "—"


def test_message_summary_callsign_and_alt():
    ac = Aircraft(icao="4840D6", callsign="KLM1023", altitude_ft=35000)
    summary = message_summary(ac)
    assert "KLM1023" in summary
    assert "35,000 ft" in summary

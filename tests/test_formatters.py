from __future__ import annotations

from aircraftx.models.aircraft import Aircraft
from aircraftx.ui.formatters import fmt_optional, message_summary


def test_fmt_optional_missing():
    assert fmt_optional(None) == "—"


def test_fmt_optional_float():
    assert fmt_optional(123.456, "°") == "123.5°"


def test_message_summary_callsign_and_alt():
    ac = Aircraft(icao="4840D6", callsign="KLM1023", altitude_ft=35000)
    summary = message_summary(ac)
    assert "KLM1023" in summary
    assert "35,000 ft" in summary

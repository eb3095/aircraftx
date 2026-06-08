from __future__ import annotations

from aircraftx.decode.labels import table_type_is_adsb, table_type_label
from aircraftx.models.aircraft import Aircraft


def test_adsb_table_keeps_adsb_type_after_mode_s_reply():
    ac = Aircraft(icao="406B90")
    ac.df17_count = 3
    ac.last_adsb_df = 17
    ac.last_adsb_tc = 4
    ac.last_df = 11
    ac.last_tc = None

    assert table_type_label(ac, adsb_table=True) == "ADS-B/4"
    assert table_type_is_adsb(ac, adsb_table=True) is True
    assert table_type_label(ac, adsb_table=False) == "all-call"


def test_mode_s_table_uses_latest_reply():
    ac = Aircraft(icao="A0C669")
    ac.last_df = 4
    ac.last_tc = None

    assert table_type_label(ac, adsb_table=False) == "Mode-S alt"
    assert table_type_is_adsb(ac, adsb_table=False) is False

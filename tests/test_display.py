from __future__ import annotations

import time
from io import StringIO
from unittest.mock import patch

from rich.console import Console

from aircraftx.config import SnifferConfig
from aircraftx.decode.tracker import AircraftTracker
from aircraftx.models.aircraft import Aircraft
from aircraftx.ui.display import PAGE_SIZE, ConsoleDisplay
from aircraftx.ui.sounds import DiscoverySound


def test_hint_shows_mode_s_count_in_adsb_view():
    config = SnifferConfig.from_preset(indoor=True, adsb_only=True)
    display = ConsoleDisplay(config)
    tracker = AircraftTracker()
    for i in range(3):
        ac = Aircraft(icao=f"{i:06X}", first_seen=time.time())
        ac.last_df = 11
        ac.message_count = 1
        tracker.aircraft[ac.icao] = ac

    hint = display._hint_panel(tracker, time.time())
    assert hint is not None
    buf = Console(file=StringIO(), width=120, record=True)
    buf.print(hint)
    rendered = buf.export_text()
    assert "3" in rendered
    assert "Mode-S" in rendered
    assert "Press a" in rendered or "press a" in rendered.lower()


def test_push_message_tracks_recent_newest_on_top():
    config = SnifferConfig.from_preset(adsb_only=False)
    display = ConsoleDisplay(config)
    ac1 = Aircraft(icao="AAAAAA")
    ac1.last_df = 11
    ac2 = Aircraft(icao="BBBBBB")
    ac2.last_df = 11

    display.push_message(ac1, 100.0)
    display.push_message(ac2, 101.0)

    assert [m.icao for m in display.recent_mode_s] == ["AAAAAA", "BBBBBB"]
    panel = display._recent_panel()
    rendered = Console(file=StringIO(), width=120, record=True)
    rendered.print(panel)
    text = rendered.export_text()
    assert text.index("BBBBBB") < text.index("AAAAAA")


def test_adsb_messages_not_evicted_by_mode_s_flood():
    config = SnifferConfig.from_preset(adsb_only=True)
    display = ConsoleDisplay(config)
    adsb = Aircraft(icao="ADS001")
    adsb.last_df = 17
    adsb.last_adsb_df = 17
    display.push_message(adsb, 100.0)

    for i in range(600):
        mode_s = Aircraft(icao=f"{i:06X}")
        mode_s.last_df = 11
        display.push_message(mode_s, 100.0 + i)

    assert len(display.recent_adsb) == 1
    assert display.recent_adsb[0].icao == "ADS001"
    assert len(display.recent_mode_s) == 500


def test_aircraft_table_pagination_oldest_first():
    config = SnifferConfig.from_preset(adsb_only=False)
    display = ConsoleDisplay(config)
    display.newest_first = False
    tracker = AircraftTracker()
    now = 1000.0
    ordered = []
    for i in range(PAGE_SIZE + 3):
        ac = Aircraft(icao=f"{i:06X}", first_seen=now + i)
        ac.last_df = 11
        ac.message_count = 1
        ac.last_seen = now + i
        tracker.aircraft[ac.icao] = ac
        ordered.append(ac)

    display.page_index = 1
    table = display._aircraft_table(ordered, now + PAGE_SIZE)
    assert "page 2/2" in table.title
    assert len(table.rows) == 3


def test_latest_mode_keeps_page_one():
    config = SnifferConfig.from_preset(adsb_only=False)
    display = ConsoleDisplay(config)
    display.newest_first = True
    display.page_index = 0
    display.sync_page(PAGE_SIZE + 5)
    assert display.page_index == 0


def test_ordered_aircraft_newest_first():
    config = SnifferConfig.from_preset(adsb_only=False)
    display = ConsoleDisplay(config)
    display.newest_first = True
    tracker = AircraftTracker()
    now = 1000.0
    old = Aircraft(icao="OLD001", first_seen=now)
    old.last_df = 11
    old.message_count = 1
    new = Aircraft(icao="NEW001", first_seen=now + 10)
    new.last_df = 11
    new.message_count = 1
    tracker.aircraft["NEW001"] = new
    tracker.aircraft["OLD001"] = old

    ordered = display._ordered_aircraft(tracker, now + 20)
    assert [ac.icao for ac in ordered] == ["NEW001", "OLD001"]


def test_g_and_g_keys_switch_sort_and_reset_page():
    config = SnifferConfig.from_preset(adsb_only=False)
    display = ConsoleDisplay(config)
    display.page_index = 2
    display.handle_key("first", 100)
    assert display.newest_first is False
    assert display.page_index == 0
    display.handle_key("last", 100)
    assert display.newest_first is True
    assert display.page_index == 0


def test_adsb_discovery_sound_once_per_icao():
    config = SnifferConfig.from_preset(adsb_only=True, sound_enabled=True)
    display = ConsoleDisplay(config)
    ac = Aircraft(icao="ABC123")
    ac.last_df = 17

    with patch.object(DiscoverySound, "play") as play:
        display.push_message(ac, 100.0)
        display.push_message(ac, 101.0)
        assert play.call_count == 1


def test_no_sound_for_mode_s_only():
    config = SnifferConfig.from_preset(sound_enabled=True)
    display = ConsoleDisplay(config)
    ac = Aircraft(icao="ABC123")
    ac.last_df = 11

    with patch.object(DiscoverySound, "play") as play:
        display.push_message(ac, 100.0)
        assert play.call_count == 0

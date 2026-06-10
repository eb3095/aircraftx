from __future__ import annotations

import time
from io import StringIO
from unittest.mock import patch

from rich.console import Console

from aircraftx.config import SnifferConfig
from aircraftx.decode.tracker import AircraftTracker
from aircraftx.models.aircraft import Aircraft
from aircraftx.lookup.models import AircraftEnrichment
from aircraftx.lookup.service import AircraftLookupService
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
    tracker = AircraftTracker()
    now = 1000.0
    display.page_index = 2
    display.handle_key("first", tracker, now)
    assert display.newest_first is False
    assert display.page_index == 0
    display.handle_key("last", tracker, now)
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


def test_enrichment_panel_only_in_adsb_mode():
    config = SnifferConfig.from_preset(adsb_only=True)
    lookup = AircraftLookupService()
    try:
        display = ConsoleDisplay(config, lookup=lookup)
        tracker = AircraftTracker()
        now = 1000.0
        ac = Aircraft(icao="4010EE", callsign="EZY1", first_seen=now)
        ac.last_df = 17
        ac.df17_count = 1
        ac.message_count = 1
        tracker.aircraft["4010EE"] = ac
        lookup.sync_active_icaos({"4010EE"})
        with lookup._lock:
            lookup._cache["4010EE"] = AircraftEnrichment(
                icao="4010EE",
                status="ready",
                registration="G-EZBZ",
                manufacturer="Airbus",
                route="EGLL-EIDW",
                departure="EGLL",
                destination="EIDW",
            )
        display.last_discovered_icao = "4010EE"
        group = display.render(tracker, now, config.radio)
        rendered = Console(file=StringIO(), width=120, record=True)
        rendered.print(group)
        text = rendered.export_text()
        assert "Aircraft Details" in text
        assert "G-EZBZ" in text
        assert "EGLL" in text
    finally:
        lookup.shutdown()


def test_mode_s_view_hides_enrichment_panel():
    config = SnifferConfig.from_preset(adsb_only=False)
    lookup = AircraftLookupService()
    try:
        display = ConsoleDisplay(config, lookup=lookup)
        tracker = AircraftTracker()
        now = 1000.0
        ac = Aircraft(icao="MODE01", first_seen=now)
        ac.last_df = 11
        ac.message_count = 1
        tracker.aircraft["MODE01"] = ac
        display.last_discovered_icao = "MODE01"
        group = display.render(tracker, now, config.radio)
        rendered = Console(file=StringIO(), width=120, record=True)
        rendered.print(group)
        text = rendered.export_text()
        assert "Aircraft Details" not in text
    finally:
        lookup.shutdown()


def test_deselect_clears_highlight():
    config = SnifferConfig.from_preset(adsb_only=True)
    lookup = AircraftLookupService()
    try:
        display = ConsoleDisplay(config, lookup=lookup)
        tracker = AircraftTracker()
        now = 1000.0
        ac = Aircraft(icao="4010EE", first_seen=now)
        ac.last_df = 17
        ac.df17_count = 1
        ac.message_count = 1
        tracker.aircraft["4010EE"] = ac
        display.last_discovered_icao = "4010EE"
        display.handle_key("channel_down", tracker, now)
        assert display._highlight_icao(display._ordered_aircraft(tracker, now)) == "4010EE"
        display.handle_key("deselect", tracker, now)
        assert display._highlight_icao(display._ordered_aircraft(tracker, now)) is None
        assert display._focus_icao(display._ordered_aircraft(tracker, now)) == "4010EE"
    finally:
        lookup.shutdown()


def test_first_arrow_down_selects_top_row():
    config = SnifferConfig.from_preset(adsb_only=True)
    display = ConsoleDisplay(config)
    tracker = AircraftTracker()
    now = 1000.0
    old = Aircraft(icao="OLD001", first_seen=now)
    old.last_df = 17
    old.df17_count = 1
    old.message_count = 1
    new = Aircraft(icao="NEW001", first_seen=now + 10)
    new.last_df = 17
    new.df17_count = 1
    new.message_count = 1
    tracker.aircraft["OLD001"] = old
    tracker.aircraft["NEW001"] = new
    display.newest_first = True
    display.last_discovered_icao = "NEW001"
    display.handle_key("channel_down", tracker, now)
    ordered = display._ordered_aircraft(tracker, now + 20)
    assert display.selected_icao == "NEW001"
    assert display.selected_index == 0
    assert ordered[0].icao == "NEW001"
    display.handle_key("channel_down", tracker, now + 20)
    assert display.selected_icao == "OLD001"
    assert display.selected_index == 1
    assert ordered[1].icao == "OLD001"


def test_selection_follows_icao_when_new_aircraft_arrives():
    config = SnifferConfig.from_preset(adsb_only=True)
    display = ConsoleDisplay(config)
    tracker = AircraftTracker()
    now = 1000.0
    old = Aircraft(icao="OLD001", first_seen=now)
    old.last_df = 17
    old.df17_count = 1
    old.message_count = 1
    tracker.aircraft["OLD001"] = old
    display.newest_first = True
    display.handle_key("channel_down", tracker, now)
    assert display.selected_icao == "OLD001"
    assert display.selected_index == 0

    newer = Aircraft(icao="NEW001", first_seen=now + 10)
    newer.last_df = 17
    newer.df17_count = 1
    newer.message_count = 1
    tracker.aircraft["NEW001"] = newer

    display.render(tracker, now + 20, config.radio)
    ordered = display._ordered_aircraft(tracker, now + 20)
    assert ordered[0].icao == "NEW001"
    assert display.selected_icao == "OLD001"
    assert display.selected_index == 1
    assert display._highlight_icao(ordered) == "OLD001"


def test_deselect_shows_latest_not_selected():
    config = SnifferConfig.from_preset(adsb_only=True)
    lookup = AircraftLookupService()
    try:
        display = ConsoleDisplay(config, lookup=lookup)
        tracker = AircraftTracker()
        now = 1000.0
        for icao in ("OLD001", "NEW001"):
            ac = Aircraft(icao=icao, first_seen=now)
            ac.last_df = 17
            ac.df17_count = 1
            ac.message_count = 1
            tracker.aircraft[icao] = ac
        display.newest_first = True
        display.last_discovered_icao = "NEW001"
        display.handle_key("channel_down", tracker, now)
        assert display.selected_icao == "NEW001"
        assert display.selected_index == 0
        display.handle_key("deselect", tracker, now)
        assert display.selected_icao is None
        assert display.selected_index is None
        assert display._focus_icao(display._ordered_aircraft(tracker, now)) == "NEW001"
    finally:
        lookup.shutdown()


def test_adsb_lookup_after_mode_s_seen():
    config = SnifferConfig.from_preset(adsb_only=True)
    lookup = AircraftLookupService()
    try:
        display = ConsoleDisplay(config, lookup=lookup)
        mode_s = Aircraft(icao="4840D6")
        mode_s.last_df = 11
        adsb = Aircraft(icao="4840D6", callsign="")
        adsb.last_df = 17
        display.push_message(mode_s, 100.0)
        display.push_message(adsb, 101.0)
        assert display.last_discovered_icao == "4840D6"
        assert "4840D6" in display._adsb_lookup_icaos
        assert lookup.pending_count() >= 1
    finally:
        lookup.shutdown()


def test_deselect_tracks_new_ping_after_mode_s():
    config = SnifferConfig.from_preset(adsb_only=True, sound_enabled=False)
    lookup = AircraftLookupService()
    try:
        display = ConsoleDisplay(config, lookup=lookup)
        display.last_discovered_icao = "OLD001"
        mode_s = Aircraft(icao="NEW001")
        mode_s.last_df = 11
        adsb = Aircraft(icao="NEW001")
        adsb.last_df = 17
        display.push_message(mode_s, 100.0)
        display.push_message(adsb, 101.0)
        assert display.selected_icao is None
        assert display.selected_index is None
        assert display.last_discovered_icao == "NEW001"
    finally:
        lookup.shutdown()


def test_no_sound_for_mode_s_only():
    config = SnifferConfig.from_preset(sound_enabled=True)
    display = ConsoleDisplay(config)
    ac = Aircraft(icao="ABC123")
    ac.last_df = 11

    with patch.object(DiscoverySound, "play") as play:
        display.push_message(ac, 100.0)
        assert play.call_count == 0

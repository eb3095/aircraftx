from __future__ import annotations

import time

from aircraftx.decode.tracker import AircraftTracker
from aircraftx.models.aircraft import Aircraft
from aircraftx.ui.display import ConsoleDisplay
from aircraftx.config import SnifferConfig


def test_tracker_ingests_mode_s_while_display_adsb_only():
    tracker = AircraftTracker()
    display = ConsoleDisplay(SnifferConfig.from_preset(adsb_only=True))
    now = time.time()

    ac = tracker.ingest("5DA0C669F4E517", now=now)
    assert ac is not None
    assert tracker.mode_s_messages == 1
    assert display._visible_confirmed(tracker, now) == []


def test_display_filters_mode_s_only_aircraft():
    tracker = AircraftTracker()
    display = ConsoleDisplay(SnifferConfig.from_preset(adsb_only=True))
    now = time.time()

    mode_s = Aircraft(icao="MODE11", first_seen=now)
    mode_s.last_df = 11
    mode_s.message_count = 1
    mode_s.altitude_ft = 35000

    adsb = Aircraft(icao="ADS017", first_seen=now + 1)
    adsb.last_df = 17
    adsb.df17_count = 2
    adsb.message_count = 2

    tracker.aircraft["MODE11"] = mode_s
    tracker.aircraft["ADS017"] = adsb

    visible = display._visible_confirmed(tracker, now + 10)
    assert len(visible) == 1
    assert visible[0].icao == "ADS017"


def test_adsb_aircraft_keeps_mode_s_fields_in_background():
    tracker = AircraftTracker()
    display = ConsoleDisplay(SnifferConfig.from_preset(adsb_only=True))
    now = time.time()

    ac = Aircraft(icao="ABC123", first_seen=now)
    ac.last_df = 17
    ac.df17_count = 2
    ac.message_count = 3
    ac.altitude_ft = 35000
    ac.hit_times.extend([now, now + 1, now + 2])
    tracker.aircraft["ABC123"] = ac

    visible = display._visible_confirmed(tracker, now + 5)
    assert len(visible) == 1
    assert visible[0].altitude_ft == 35000

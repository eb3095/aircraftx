from __future__ import annotations

import time

from aircraftx.config import MAX_ADSB_TRACKS, MAX_MODE_S_TRACKS
from aircraftx.decode.tracker import AircraftTracker
from aircraftx.models.aircraft import Aircraft


def test_mode_s_track_cap_evicts_oldest():
    tracker = AircraftTracker()
    now = time.time()
    for i in range(MAX_MODE_S_TRACKS + 50):
        ac = Aircraft(icao=f"{i:06X}", first_seen=now + i)
        ac.last_df = 11
        ac.message_count = 1
        ac.last_seen = now + i
        tracker.aircraft[ac.icao] = ac
    tracker._enforce_track_caps()

    mode_s = [ac for ac in tracker.aircraft.values() if ac.df17_count == 0]
    assert len(mode_s) == MAX_MODE_S_TRACKS
    assert all(ac.last_seen >= now + 50 for ac in mode_s)


def test_adsb_track_cap_evicts_oldest():
    tracker = AircraftTracker()
    now = time.time()
    for i in range(MAX_ADSB_TRACKS + 25):
        ac = Aircraft(icao=f"{i:06X}", first_seen=now + i)
        ac.last_df = 17
        ac.df17_count = 1
        ac.last_seen = now + i
        tracker.aircraft[ac.icao] = ac
    tracker._enforce_track_caps()

    adsb = [ac for ac in tracker.aircraft.values() if ac.df17_count > 0]
    assert len(adsb) == MAX_ADSB_TRACKS
    assert all(ac.last_seen >= now + 25 for ac in adsb)

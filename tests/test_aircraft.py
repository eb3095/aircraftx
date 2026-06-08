from __future__ import annotations

import time

from aircraftx.models.aircraft import Aircraft


def test_aircraft_confirmed_after_enough_hits():
    ac = Aircraft(icao="ABC123")
    now = time.time()
    ac.hit_times.append(now)
    ac.hit_times.append(now + 1)
    assert ac.is_confirmed(now + 2, min_hits=2) is True


def test_aircraft_confirmed_on_single_df17():
    ac = Aircraft(icao="ABC123")
    ac.df17_count = 1
    ac.last_df = 17
    assert ac.is_confirmed(time.time(), min_hits=5) is True


def test_aircraft_confirmed_on_two_df17():
    ac = Aircraft(icao="ABC123")
    ac.df17_count = 2
    ac.last_df = 17
    assert ac.is_confirmed(time.time(), min_hits=5) is True


def test_aircraft_confirmed_on_single_mode_s_reply():
    ac = Aircraft(icao="ABC123")
    ac.last_df = 11
    ac.message_count = 1
    assert ac.is_confirmed(time.time(), min_hits=3) is True


def test_recent_hits_expires_old():
    ac = Aircraft(icao="ABC123")
    now = 1000.0
    ac.hit_times.append(now - 100)
    ac.hit_times.append(now - 50)
    ac.hit_times.append(now)
    assert ac.recent_hits(now, window=45.0) == 1

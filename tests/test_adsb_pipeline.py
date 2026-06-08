from __future__ import annotations

import time
from unittest.mock import patch

import pyModeS as pms

from aircraftx.app.sniffer import AircraftXSniffer
from aircraftx.config import SnifferConfig
from aircraftx.decode.tracker import AircraftTracker
from aircraftx.ui.display import ConsoleDisplay
from aircraftx.ui.sounds import DISCOVERY_SOUNDS, DiscoverySound

DF17 = "8D406B902015A678D4D220AA4BDA"


def test_single_df17_appears_in_adsb_table():
    tracker = AircraftTracker()
    display = ConsoleDisplay(SnifferConfig.from_preset(adsb_only=True))
    now = time.time()

    ac = tracker.ingest(DF17, now=now)
    assert ac is not None
    assert ac.df17_count == 1
    assert pms.decode(DF17).get("df") == 17

    visible = display._confirmed_adsb(tracker, now)
    assert len(visible) == 1
    assert visible[0].icao == ac.icao


def test_mode_s_reply_after_adsb_stays_in_adsb_table():
    tracker = AircraftTracker()
    display = ConsoleDisplay(SnifferConfig.from_preset(adsb_only=True))
    now = time.time()

    tracker.ingest(DF17, now=now)
    ac = tracker.aircraft["406B90"]
    # Same ICAO: later radar reply updates last_df but not ADS-B membership.
    ac.last_df = 11
    ac.message_count += 1
    ac.hit_times.append(now + 1)
    ac.last_seen = now + 1

    assert ac.df17_count == 1
    assert ac.last_adsb_df == 17

    visible = display._confirmed_adsb(tracker, now + 2)
    assert len(visible) == 1
    assert display._confirmed_mode_s(tracker, now + 2) == []


def test_mode_s_reply_does_not_count_as_adsb():
    tracker = AircraftTracker()
    display = ConsoleDisplay(SnifferConfig.from_preset(adsb_only=True))
    now = time.time()

    tracker.ingest("5DA0C669F4E517", now=now)

    assert display._confirmed_adsb(tracker, now) == []
    assert len(display._confirmed_mode_s(tracker, now)) == 1


def test_sniffer_plays_sound_on_first_df17_only():
    """End-to-end: ingest -> push_message -> DiscoverySound.play once per ICAO."""
    sniffer = AircraftXSniffer(SnifferConfig.from_preset(sound_enabled=True))
    now = time.time()

    with patch.object(DiscoverySound, "play") as play:
        sniffer._process_messages([DF17], now)
        sniffer._process_messages([DF17], now + 1)
        assert play.call_count == 1


def test_sniffer_no_sound_for_mode_s_or_when_disabled():
    now = time.time()
    mode_s = "5DA0C669F4E517"

    with patch.object(DiscoverySound, "play") as play:
        sniffer = AircraftXSniffer(SnifferConfig.from_preset(sound_enabled=True))
        sniffer._process_messages([mode_s], now)
        assert play.call_count == 0

    with patch.object(DiscoverySound, "play") as play:
        sniffer = AircraftXSniffer(SnifferConfig.from_preset(sound_enabled=False))
        sniffer._process_messages([DF17], now)
        assert play.call_count == 0


def test_discovery_sound_invokes_afplay_on_macos():
    with patch("subprocess.Popen") as popen:
        DiscoverySound.play()
    popen.assert_called_once()
    cmd = popen.call_args[0][0]
    assert cmd[:2] == ["afplay", DISCOVERY_SOUNDS[0]]

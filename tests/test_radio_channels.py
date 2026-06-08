from __future__ import annotations

from aircraftx.radio.channels import COMMON_AIRBAND_CHANNELS


def test_common_channels_have_unique_ids():
    ids = [ch.channel_id for ch in COMMON_AIRBAND_CHANNELS]
    assert len(ids) == len(set(ids))


def test_channel_freq_in_airband():
    for ch in COMMON_AIRBAND_CHANNELS:
        assert 118_000_000 <= ch.freq_hz <= 137_000_000


def test_guard_channel_in_defaults():
    ch = next(c for c in COMMON_AIRBAND_CHANNELS if c.channel_id == "121.500")
    assert ch.name == "Emergency (Guard)"

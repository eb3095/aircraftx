from __future__ import annotations

import time
from unittest.mock import patch

import numpy as np

from aircraftx.config import MAX_RADIO_TRANSCRIPTS, RADIO_CHANNEL_PAGE_SIZE
from aircraftx.radio.channels import COMMON_AIRBAND_CHANNELS
from aircraftx.radio.voice_monitor import TranscriptLine, VoiceMonitor


def test_per_channel_buffer_cap():
    monitor = VoiceMonitor(basic_channels=COMMON_AIRBAND_CHANNELS)
    monitor.set_channel_source("basic")
    ch_a = monitor.channels[0].channel_id
    ch_b = monitor.channels[1].channel_id
    buf = monitor._buffers[ch_a]

    for i in range(MAX_RADIO_TRANSCRIPTS + 5):
        buf.append(TranscriptLine(timestamp="t", text=str(i), channel_id=ch_a))
    assert len(buf) == MAX_RADIO_TRANSCRIPTS
    assert buf[-1].text == str(MAX_RADIO_TRANSCRIPTS + 4)
    assert len(monitor.buffer_for(ch_b)) == 0


def test_channel_select_retunes_index():
    monitor = VoiceMonitor(basic_channels=COMMON_AIRBAND_CHANNELS)
    monitor.set_channel_source("basic")
    last = len(monitor.channels) - 1
    monitor.select_index(last)
    assert monitor.selected_index == last
    monitor.channel_up()
    assert monitor.selected_index == last - 1


def test_channel_source_defaults_local():
    monitor = VoiceMonitor(
        local_channels=[COMMON_AIRBAND_CHANNELS[0]],
        basic_channels=COMMON_AIRBAND_CHANNELS[1:3],
    )
    assert monitor.channel_source == "local"
    assert (
        monitor.active_channels[0].channel_id == COMMON_AIRBAND_CHANNELS[0].channel_id
    )
    monitor.set_channel_source("basic")
    assert (
        monitor.active_channels[0].channel_id == COMMON_AIRBAND_CHANNELS[1].channel_id
    )


def test_channel_pagination():
    many = COMMON_AIRBAND_CHANNELS * 2
    monitor = VoiceMonitor(basic_channels=many)
    monitor.set_channel_source("basic")
    monitor.select_index(RADIO_CHANNEL_PAGE_SIZE)
    assert monitor.page_index == 1
    assert len(monitor.page_channels()) <= RADIO_CHANNEL_PAGE_SIZE
    monitor.channel_page_up()
    assert monitor.page_index == 0


def test_process_iq_queues_transcription():
    from aircraftx.radio.transcriber import StubTranscriber

    monitor = VoiceMonitor()
    monitor._transcriber = StubTranscriber()
    audio = np.ones(8_000, dtype=np.float32) * 0.5
    segments = [audio]

    with (
        patch("aircraftx.radio.voice_monitor.demod_am", return_value=audio),
        patch(
            "aircraftx.radio.voice_monitor.IQConverter.from_bytes",
            return_value=np.ones(100, dtype=np.complex64),
        ),
        patch.object(monitor._segmenter, "feed", return_value=segments),
        patch.object(
            monitor._transcriber, "transcribe", return_value="N12345 runway two seven"
        ),
    ):
        monitor.process_iq(b"\x00" * 200, now=time.time())
        time.sleep(0.1)

    lines = list(monitor.buffer_for())
    assert len(lines) == 1
    assert "N12345" in lines[0].text

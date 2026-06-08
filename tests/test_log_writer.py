from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import numpy as np

from aircraftx.acars.decoder import AcarsMessage, ETX, STX, parse_acars_block
from aircraftx.config import SnifferConfig
from aircraftx.log_writer import LogWriter, mhz_log_name
from aircraftx.models.aircraft import Aircraft
from aircraftx.radio.channels import COMMON_AIRBAND_CHANNELS
from aircraftx.radio.voice_monitor import VoiceMonitor
from aircraftx.ui.display import ConsoleDisplay


def test_mhz_log_name():
    assert mhz_log_name("radio", 118.5) == "radio_118.500"
    assert mhz_log_name("acars", 131.55) == "acars_131.550"


def test_adsb_and_mode_s_logs(tmp_path: Path):
    writer = LogWriter(tmp_path)
    config = SnifferConfig.from_preset(adsb_only=True)
    display = ConsoleDisplay(config, writer)

    adsb = Aircraft(icao="ABC123", callsign="UAL1", altitude_ft=10000)
    adsb.last_df = 17
    display.push_message(adsb, 1_700_000_000.0)

    config_mode_s = SnifferConfig.from_preset(adsb_only=False)
    display_ms = ConsoleDisplay(config_mode_s, writer)
    mode_s = Aircraft(icao="DEF456")
    mode_s.last_df = 11
    display_ms.push_message(mode_s, 1_700_000_000.0)

    writer.close()

    adsb_log = (tmp_path / "ads_b.log").read_text(encoding="utf-8")
    mode_s_log = (tmp_path / "mode_s.log").read_text(encoding="utf-8")
    assert "ABC123" in adsb_log
    assert "ADS-B" in adsb_log
    assert "DEF456" in mode_s_log
    assert "all-call" in mode_s_log


def test_acars_log_per_frequency(tmp_path: Path):
    writer = LogWriter(tmp_path)
    txt = b"2N12345.!H11" + bytes([STX]) + b"A001UAL123HELLO" + bytes([ETX])
    message = parse_acars_block(txt)
    assert message is not None
    writer.log_acars(131.55, "12:00:00", message)
    writer.close()

    path = tmp_path / "acars_131.550.log"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "N12345" in text
    assert "HELLO" in text


def test_radio_logs_transcript_only(tmp_path: Path):
    writer = LogWriter(tmp_path)
    monitor = VoiceMonitor(
        basic_channels=COMMON_AIRBAND_CHANNELS[:1],
        log_writer=writer,
    )
    monitor.set_channel_source("basic")
    monitor._transcriber = type(
        "Stub",
        (),
        {"transcribe": staticmethod(lambda _audio: "cleared for takeoff")},
    )()
    audio = np.ones(8_000, dtype=np.float32) * 0.5

    with (
        patch("aircraftx.radio.voice_monitor.demod_am", return_value=audio),
        patch(
            "aircraftx.radio.voice_monitor.IQConverter.from_bytes",
            return_value=np.ones(100, dtype=np.complex64),
        ),
        patch.object(monitor._segmenter, "feed", return_value=[audio]),
    ):
        monitor.process_iq(b"\x00" * 200, now=time.time())
        time.sleep(0.15)

    writer.close()
    channel = monitor.selected_channel()
    log_path = tmp_path / f"radio_{channel.freq_mhz:.3f}.log"
    assert log_path.exists()
    assert log_path.read_text(encoding="utf-8").strip() == "cleared for takeoff"

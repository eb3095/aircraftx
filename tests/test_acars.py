from __future__ import annotations

from io import StringIO

from rich.console import Console

from aircraftx.acars.channel_defaults import DEFAULT_ACARS_CHANNELS
from aircraftx.acars.channels import parse_acars_channels
from aircraftx.acars.decoder import ETX, STX, parse_acars_block
from aircraftx.acars.monitor import AcarsMonitor
from aircraftx.config import MAX_ACARS_MESSAGES, SnifferConfig
from aircraftx.ui.acars_display import AcarsDisplay


def test_parse_acars_block_downlink():
    txt = b"2N12345.!H11" + bytes([STX]) + b"A001UAL123/TE TEST MESSAGE" + bytes([ETX])
    msg = parse_acars_block(txt)
    assert msg is not None
    assert msg.tail == "N12345"
    assert msg.label == "H1"
    assert msg.flight == "UAL123"
    assert msg.msgno == "A001"
    assert "TEST MESSAGE" in msg.text


def test_parse_acars_channels_from_config():
    channels = parse_acars_channels(DEFAULT_ACARS_CHANNELS[:2])
    assert len(channels) == 2
    assert channels[0].channel_id == "131.550"


def test_acars_monitor_channel_select_retunes_index():
    monitor = AcarsMonitor()
    last = len(monitor.channels) - 1
    monitor.select_index(last)
    assert monitor.selected_index == last
    monitor.channel_up()
    assert monitor.selected_index == last - 1


def test_acars_message_buffer_cap():
    monitor = AcarsMonitor(channels=parse_acars_channels(DEFAULT_ACARS_CHANNELS[:1]))
    ch = monitor.channels[0].channel_id
    txt = b"2N12345.!H11" + bytes([STX]) + b"A001UAL123MSG" + bytes([ETX])
    parsed = parse_acars_block(txt)
    assert parsed is not None
    from aircraftx.acars.monitor import AcarsLine

    for i in range(MAX_ACARS_MESSAGES + 3):
        monitor.buffer_for(ch).append(AcarsLine(timestamp="12:00:00", message=parsed))
    assert len(monitor.buffer_for(ch)) == MAX_ACARS_MESSAGES


def test_acars_display_renders():
    monitor = AcarsMonitor(channels=parse_acars_channels(DEFAULT_ACARS_CHANNELS[:2]))
    display = AcarsDisplay(monitor, SnifferConfig.from_preset().radio)
    console = Console(file=StringIO(), width=120, record=True)
    console.print(display.render())
    text = console.export_text()
    assert "ACARS" in text
    assert "131.550" in text

from __future__ import annotations

from io import StringIO

from rich.console import Console

from aircraftx.config import SnifferConfig
from aircraftx.radio.voice_monitor import TranscriptLine, VoiceMonitor
from aircraftx.ui.radio_display import RadioDisplay


def test_radio_dashboard_renders_channel_and_transcript():
    monitor = VoiceMonitor()
    channel = monitor.selected_channel()
    monitor.buffer_for(channel.channel_id).append(
        TranscriptLine(
            timestamp="12:00:00",
            text="N12345 cleared for takeoff",
            channel_id=channel.channel_id,
        )
    )
    display = RadioDisplay(monitor, SnifferConfig.from_preset().radio)
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=True)
    console.print(display.render())
    text = buf.getvalue()
    assert "VHF Radio Monitor" in text
    assert channel.name in text
    assert "N12345 cleared for takeoff" in text
    assert "D ADS-B" in text
    assert "Signal" in text

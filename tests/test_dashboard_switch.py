from __future__ import annotations

from aircraftx.app.sniffer import AircraftXSniffer
from aircraftx.config import FREQ_HZ, SnifferConfig


def test_dashboard_switch_retunes_hackrf():
    sniffer = AircraftXSniffer(SnifferConfig.from_preset())
    assert sniffer.dashboard == "adsb"
    assert sniffer.receiver.freq_hz == FREQ_HZ

    sniffer.set_dashboard("radio")
    assert sniffer.dashboard == "radio"
    assert sniffer.receiver.freq_hz == sniffer.voice_monitor.selected_channel().freq_hz

    sniffer.set_dashboard("adsb")
    assert sniffer.receiver.freq_hz == FREQ_HZ

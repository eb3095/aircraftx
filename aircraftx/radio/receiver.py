from __future__ import annotations

from aircraftx.config import RadioConfig
from aircraftx.radio.hackrf import HackRFReceiver
from aircraftx.radio.rtlsdr import RtlSdrReceiver


def make_receiver(
    config: RadioConfig,
    *,
    freq_hz: int,
    sample_rate: int | None = None,
):
    backend = (config.backend or "hackrf").strip().lower()
    kwargs = {"freq_hz": freq_hz}
    if sample_rate is not None:
        kwargs["sample_rate"] = sample_rate
    if backend in {"rtl", "rtlsdr", "rtl-sdr"}:
        return RtlSdrReceiver(config, **kwargs)
    return HackRFReceiver(config, **kwargs)

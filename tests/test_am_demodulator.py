from __future__ import annotations

import numpy as np

from aircraftx.config import AIRBAND_AUDIO_RATE, SAMPLE_RATE
from aircraftx.dsp.am_demodulator import AMDemodulator, demod_am


def _am_iq(mod_depth: float = 0.4) -> np.ndarray:
    t = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    mod = 0.5 + mod_depth * np.sin(2 * np.pi * 300 * t)
    carrier = np.exp(2j * np.pi * 0.0 * t).astype(np.complex64)
    return (carrier * mod * 127.0).astype(np.complex64)


def test_demod_am_produces_16k_audio():
    audio = demod_am(_am_iq())
    expected_len = SAMPLE_RATE // (SAMPLE_RATE // AIRBAND_AUDIO_RATE)
    assert audio.dtype == np.float32
    assert audio.size == expected_len
    assert float(np.max(np.abs(audio))) <= 1.0
    assert float(np.max(np.abs(audio))) > 0.05


def test_demod_preserves_level_differences_not_peak_normalized():
    quiet = AMDemodulator()
    loud = AMDemodulator()
    quiet_audio = quiet.demod(_am_iq(mod_depth=0.02))
    loud_audio = loud.demod(_am_iq(mod_depth=0.6))
    quiet_rms = float(np.sqrt(np.mean(quiet_audio**2)))
    loud_rms = float(np.sqrt(np.mean(loud_audio**2)))
    assert loud_rms > quiet_rms * 1.5

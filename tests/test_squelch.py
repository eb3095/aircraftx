from __future__ import annotations

import time

import numpy as np

from aircraftx.radio.squelch import SquelchGate


def _static_chunk(rms: float = 0.15, size: int = 4_000) -> np.ndarray:
    return np.full(size, rms, dtype=np.float32)


def test_squelch_silences_quiet_audio():
    gate = SquelchGate(snr_db=20.0)
    quiet = np.zeros(1_000, dtype=np.float32) + 1e-5
    for _ in range(8):
        gated, _, open_ = gate.gate_audio(quiet)
    assert open_ is False
    assert float(np.max(np.abs(gated))) < 0.05


def test_squelch_adjust_clamps():
    gate = SquelchGate(snr_db=10.0)
    gate.adjust(50.0)
    assert gate.snr_db == gate.max_snr_db
    gate.adjust(-100.0)
    assert gate.snr_db == gate.min_snr_db


def test_squelch_close_threshold_lower_than_open():
    gate = SquelchGate(snr_db=8.0, hysteresis_db=6.0)
    assert gate._close_threshold() < gate._open_threshold()


def test_squelch_gain_fades_not_hard_switch():
    gate = SquelchGate(snr_db=14.0)
    gate._warmup_left = 0
    gate._gate_open = True
    gate._gain = 0.5
    audio = np.ones(100, dtype=np.float32) * 0.8
    gated, _, _ = gate.gate_audio(audio)
    peak = float(np.max(np.abs(gated)))
    assert 0.0 < peak < 0.8


def test_squelch_mutes_constant_static_at_high_setting():
    gate = SquelchGate(snr_db=14.0)
    static = _static_chunk(0.15)
    t0 = time.monotonic()
    for i in range(40):
        gated, _, open_ = gate.gate_audio(static, now=t0 + i * 0.05)
    assert gate._noise_floor > 0.05
    assert open_ is False
    assert float(np.max(np.abs(gated))) < 0.02


def test_squelch_opens_for_loud_burst():
    gate = SquelchGate(snr_db=14.0)
    static = _static_chunk(0.15)
    t0 = time.monotonic()
    for i in range(30):
        gate.gate_audio(static, now=t0 + i * 0.05)
    speech = _static_chunk(0.9)
    _, _, open_ = gate.gate_audio(speech, now=t0 + 2.0)
    assert open_ is True

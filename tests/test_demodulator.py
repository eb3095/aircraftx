from __future__ import annotations

import numpy as np

from aircraftx.config import DemodSettings, PREAMBLE_LEN
from aircraftx.dsp.demodulator import ModeSDemodulator


def test_bits_to_hex():
    bits = [1, 0, 0, 0] * 28  # 112 bits -> 28 hex chars
    assert len(ModeSDemodulator._bits_to_hex(bits)) == 28


def test_validate_preamble_accepts_strong_pulse_pattern():
    demod = ModeSDemodulator(DemodSettings.outdoor())
    mag = np.zeros(PREAMBLE_LEN + 50, dtype=np.float64)
    for idx in (0, 2, 7, 9):
        mag[idx] = 10.0
    assert demod._validate_preamble_shape(mag, 0) is True


def test_validate_preamble_rejects_flat_noise():
    demod = ModeSDemodulator(DemodSettings.outdoor())
    mag = np.ones(PREAMBLE_LEN + 50, dtype=np.float64)
    assert demod._validate_preamble_shape(mag, 0) is False


def test_demodulate_empty_buffer():
    demod = ModeSDemodulator(DemodSettings.outdoor())
    assert demod.demodulate(np.array([], dtype=np.complex64)) == []


def _synthesize_short_message(hex_msg: str, preamble_start: int = 200) -> np.ndarray:
    bits: list[int] = []
    for char in hex_msg:
        value = int(char, 16)
        for shift in (3, 2, 1, 0):
            bits.append((value >> shift) & 1)

    mag = np.ones(800) * 0.3
    for idx in (0, 2, 7, 9):
        mag[preamble_start + idx] = 12.0
    data_start = preamble_start + PREAMBLE_LEN
    for i, bit in enumerate(bits):
        early = data_start + i * 2
        late = early + 1
        if bit == 1:
            mag[early], mag[late] = 10.0, 0.3
        else:
            mag[early], mag[late] = 0.3, 10.0
    return mag.astype(np.complex64)


def test_demodulate_short_mode_s():
    """56-bit replies must decode alongside long ADS-B frames."""
    hex_msg = "5DA0C669F4E517"
    demod = ModeSDemodulator(DemodSettings.indoor())
    iq = _synthesize_short_message(hex_msg)
    assert demod.demodulate(iq) == [hex_msg]


def test_pick_candidate_prefers_long_adsb():
    demod = ModeSDemodulator(DemodSettings.outdoor())
    short = "5DA0C669F4E517"
    long_adsb = "8D406B902015A678D4D220AA4BDA"
    picked = demod._pick_candidate([short, long_adsb])
    assert picked == long_adsb


def test_demodulate_long_adsb_frame():
    hex_msg = "8D406B902015A678D4D220AA4BDA"
    demod = ModeSDemodulator(DemodSettings.indoor())
    iq = _synthesize_short_message(hex_msg, preamble_start=200)
    assert demod.demodulate(iq) == [hex_msg]

from __future__ import annotations

import numpy as np

from aircraftx.dsp.waveform import WaveformScope


def test_waveform_renders_braille_scope():
    scope = WaveformScope(columns=40)
    t = np.linspace(0, 0.05, 4_000, dtype=np.float32)
    audio = (0.8 * np.sin(2 * np.pi * 400 * t)).astype(np.float32)
    scope.feed(audio)
    lines = scope.render_lines(width_chars=40, height_chars=7, gate_open=True)
    assert len(lines) == 7
    plain = "\n".join(line.plain for line in lines)
    assert any(ch > "\u2800" for ch in plain)
    assert all(len(line.plain) == 40 for line in lines)


def test_waveform_empty_is_flat_grid():
    scope = WaveformScope(columns=30)
    lines = scope.render_lines(width_chars=30, height_chars=5)
    assert len(lines) == 5
    assert all(len(line.plain) == 30 for line in lines)

"""Braille oscilloscope waveform for the radio dashboard."""

from __future__ import annotations

from collections import deque
from typing import Deque, Iterator, List, Tuple

import numpy as np
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

from aircraftx.config import WAVEFORM_HEIGHT

# Braille dot layout (dx, dy, bit) within each 2×4 cell.
_BRAILLE_DOTS: Tuple[Tuple[int, int, int], ...] = (
    (0, 0, 0x01),
    (1, 0, 0x08),
    (0, 1, 0x02),
    (1, 1, 0x10),
    (0, 2, 0x04),
    (1, 2, 0x20),
    (0, 3, 0x40),
    (1, 3, 0x80),
)


class WaveformScope:
    """Rolling signed-audio buffer rendered as a multi-row braille trace."""

    def __init__(self, *, columns: int = 120) -> None:
        self._columns = columns
        self._samples: Deque[float] = deque(maxlen=columns * 8)

    def feed(self, audio: np.ndarray) -> None:
        if audio.size == 0:
            return
        mono = audio.astype(np.float32)
        step = max(1, mono.size // 64)
        for idx in range(0, mono.size, step):
            self._samples.append(float(mono[idx]))

    def _resample(self, count: int) -> np.ndarray:
        if count <= 0:
            return np.zeros(0, dtype=np.float32)
        if not self._samples:
            return np.zeros(count, dtype=np.float32)

        src = np.asarray(self._samples, dtype=np.float32)
        if src.size == 1:
            return np.full(count, src[0], dtype=np.float32)

        x_src = np.linspace(0.0, 1.0, src.size, dtype=np.float64)
        x_dst = np.linspace(0.0, 1.0, count, dtype=np.float64)
        return np.interp(x_dst, x_src, src).astype(np.float32)

    def _prepare_trace(self, width_px: int) -> np.ndarray:
        trace = self._resample(width_px)
        if trace.size == 0:
            return trace
        trace = trace - float(np.mean(trace))
        peak = float(np.max(np.abs(trace)))
        if peak > 1e-8:
            trace = trace / peak
        return np.clip(trace, -1.0, 1.0)

    def _build_masks(
        self, width_chars: int, height_chars: int
    ) -> Tuple[List[List[int]], List[List[int]]]:
        grid_w = width_chars * 2
        grid_h = height_chars * 4
        wave = [[0] * grid_w for _ in range(grid_h)]
        grid = [[0] * grid_w for _ in range(grid_h)]

        mid = (grid_h - 1) / 2.0
        for gx in range(grid_w):
            gy = int(round(mid))
            grid[gy][gx] |= 0x01

        for fraction in (0.25, 0.75):
            y = int(round((grid_h - 1) * fraction))
            for gx in range(0, grid_w, 4):
                grid[y][gx] |= 0x01

        trace = self._prepare_trace(grid_w)
        if trace.size:
            for gx, sample in enumerate(trace):
                y = (1.0 - (sample + 1.0) * 0.5) * (grid_h - 1)
                y = max(0.0, min(float(grid_h - 1), y))
                y0 = int(y)
                y1 = min(y0 + 1, grid_h - 1)
                wave[y0][gx] |= 0x02
                if y - y0 > 0.2:
                    wave[y1][gx] |= 0x02
                if gx > 0:
                    prev = (1.0 - (trace[gx - 1] + 1.0) * 0.5) * (grid_h - 1)
                    prev = max(0.0, min(float(grid_h - 1), prev))
                    py0 = int(prev)
                    py1 = min(py0 + 1, grid_h - 1)
                    for fy in range(min(py0, y0), max(py1, y1) + 1):
                        wave[fy][gx] |= 0x01

        return wave, grid

    def render_lines(
        self,
        *,
        width_chars: int,
        height_chars: int = WAVEFORM_HEIGHT,
        gate_open: bool = False,
    ) -> List[Text]:
        width_chars = max(16, width_chars)
        height_chars = max(4, height_chars)
        wave_mask, grid_mask = self._build_masks(width_chars, height_chars)
        grid_h = height_chars * 4
        grid_w = width_chars * 2

        wave_style = "bold bright_green" if gate_open else "dim"
        grid_style = "dim green" if gate_open else "dim"

        lines: List[Text] = []
        for row in range(0, grid_h, 4):
            line = Text()
            for col in range(0, grid_w, 2):
                wave_bits = 0
                grid_bits = 0
                for dx, dy, bit in _BRAILLE_DOTS:
                    gx = col + dx
                    gy = row + dy
                    if gy >= grid_h or gx >= grid_w:
                        continue
                    if wave_mask[gy][gx] & 0x02:
                        wave_bits |= bit
                    elif wave_mask[gy][gx] & 0x01:
                        wave_bits |= bit
                    if grid_mask[gy][gx]:
                        grid_bits |= bit

                value = wave_bits | grid_bits
                ch = chr(0x2800 + value)
                if wave_bits:
                    line.append(ch, style=wave_style)
                elif grid_bits:
                    line.append(ch, style=grid_style)
                else:
                    line.append(ch)
            lines.append(line)

        while len(lines) < height_chars:
            lines.append(Text(" " * width_chars))
        return lines[:height_chars]

    def render(self, width: int | None = None, *, gate_open: bool = False) -> str:
        width = width or self._columns
        return "\n".join(
            line.plain
            for line in self.render_lines(width_chars=width, gate_open=gate_open)
        )


class WaveformView:
    """Full-width fixed-height oscilloscope panel content."""

    def __init__(
        self,
        scope: WaveformScope,
        *,
        gate_open: bool,
        height: int = WAVEFORM_HEIGHT,
    ) -> None:
        self._scope = scope
        self._gate_open = gate_open
        self._height = height

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        width = max(16, options.max_width)
        rows = self._scope.render_lines(
            width_chars=width,
            height_chars=self._height,
            gate_open=self._gate_open,
        )
        body = Text()
        for idx, row in enumerate(rows):
            if idx:
                body.append("\n")
            body.append_text(row)
        yield from console.render(body, options)

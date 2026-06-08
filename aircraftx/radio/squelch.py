"""Adaptive squelch gate for airband playback and transcription."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from aircraftx.config import AIRBAND_AUDIO_RATE

_WARMUP_CHUNKS = 8


@dataclass
class SquelchGate:
    """Drop audio below an adaptive noise floor with hysteresis and smooth fades."""

    snr_db: float = 8.0
    min_snr_db: float = 0.0
    max_snr_db: float = 40.0
    step_db: float = 1.0
    hysteresis_db: float = 6.0
    hang_sec: float = 0.12
    attack_sec: float = 0.004
    release_sec: float = 0.035
    _noise_floor: float = field(default=1e-4, init=False)
    _gate_open: bool = field(default=False, init=False)
    _hang_until: float = field(default=0.0, init=False)
    _gain: float = field(default=0.0, init=False)
    _warmup_left: int = field(default=_WARMUP_CHUNKS, init=False)
    _last_rms: float = field(default=0.0, init=False)

    @property
    def gate_open(self) -> bool:
        return self._gate_open

    @property
    def last_rms(self) -> float:
        return self._last_rms

    def _open_threshold(self) -> float:
        return self._noise_floor * (10 ** (self.snr_db / 20.0))

    def _close_threshold(self) -> float:
        return self._open_threshold() * (10 ** (-self.hysteresis_db / 20.0))

    def _track_noise_floor(self, rms: float) -> None:
        if self._gate_open:
            return
        sample = max(rms, 1e-6)
        rate = 0.15 if self._noise_floor < 0.01 else 0.08
        self._noise_floor = (1.0 - rate) * self._noise_floor + rate * sample

    def gate_audio(
        self,
        audio: np.ndarray,
        sample_rate: int = AIRBAND_AUDIO_RATE,
        now: float | None = None,
    ) -> tuple[np.ndarray, float, bool]:
        """Return (smoothed gated audio, level 0–1, gate open)."""
        if audio.size == 0:
            return audio, 0.0, self._gate_open

        mono = time.monotonic() if now is None else now
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        self._last_rms = rms

        if self._warmup_left > 0:
            self._warmup_left -= 1
            self._noise_floor = 0.85 * self._noise_floor + 0.15 * rms
            self._gate_open = False
            self._gain = 0.0
            return np.zeros_like(audio), 0.0, False

        open_t = self._open_threshold()
        close_t = self._close_threshold()

        if rms >= open_t:
            self._gate_open = True
            self._hang_until = mono + self.hang_sec
        elif rms < close_t and mono >= self._hang_until:
            self._gate_open = False

        if not self._gate_open:
            self._track_noise_floor(rms)

        target = 1.0 if self._gate_open else 0.0
        dt = audio.size / sample_rate
        tau = self.attack_sec if target > self._gain else self.release_sec
        alpha = 1.0 - float(np.exp(-dt / max(tau, 1e-4)))
        self._gain += (target - self._gain) * alpha

        level = min(1.0, rms / max(open_t * 4.0, 1e-8))
        gated = (audio.astype(np.float32) * self._gain).astype(np.float32)
        return gated, level, self._gate_open

    def apply(self, audio: np.ndarray) -> np.ndarray:
        gated, _, _ = self.gate_audio(audio)
        return gated

    def reset_calibration(self, *, relearn_noise: bool = True) -> None:
        """Re-learn channel noise after retune."""
        self._warmup_left = _WARMUP_CHUNKS
        if relearn_noise:
            self._noise_floor = 1e-4
        self._gate_open = False
        self._gain = 0.0
        self._hang_until = 0.0

    def adjust(self, delta_db: float) -> float:
        self.snr_db = max(self.min_snr_db, min(self.max_snr_db, self.snr_db + delta_db))
        if self._last_rms < self._open_threshold():
            self._gate_open = False
            self._gain = 0.0
            self._hang_until = 0.0
        return self.snr_db

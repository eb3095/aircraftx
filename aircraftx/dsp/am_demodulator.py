"""AM envelope demodulation for VHF airband voice."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from aircraftx.config import AIRBAND_AUDIO_RATE, SAMPLE_RATE

# 2 MHz / 25 = 80 kHz IF bandwidth, then / 5 = 16 kHz audio (125× total decimation).
_IQ_DECIM = 25
_AUDIO_DECIM = 5
_TOTAL_DECIM = _IQ_DECIM * _AUDIO_DECIM


def _boxcar_decimate_complex(samples: np.ndarray, factor: int) -> np.ndarray:
    count = (samples.size // factor) * factor
    if count == 0:
        return np.array([], dtype=np.complex64)
    return samples[:count].reshape(-1, factor).mean(axis=1).astype(np.complex64)


def _boxcar_decimate_real(samples: np.ndarray, factor: int) -> np.ndarray:
    count = (samples.size // factor) * factor
    if count == 0:
        return np.array([], dtype=np.float64)
    return samples[:count].reshape(-1, factor).mean(axis=1)


@dataclass
class AMDemodulator:
    """Narrowband AM demod with slow AGC — preserves real level differences for squelch."""

    agc_gain: float = field(default=1.0, init=False)
    _agc_min: float = 0.02
    _agc_max: float = 80.0
    _target_rms: float = 0.18

    def reset(self) -> None:
        self.agc_gain = 1.0

    def demod(
        self,
        iq: np.ndarray,
        sample_rate: int = SAMPLE_RATE,
        audio_rate: int = AIRBAND_AUDIO_RATE,
    ) -> np.ndarray:
        if iq.size == 0:
            return np.array([], dtype=np.float32)

        expected_decim = max(1, sample_rate // audio_rate)
        iq_decim = (
            _IQ_DECIM if expected_decim == _TOTAL_DECIM else max(1, expected_decim // 5)
        )
        audio_decim = max(1, expected_decim // iq_decim)

        scaled = iq.astype(np.complex64) / 128.0
        narrow = _boxcar_decimate_complex(scaled, iq_decim)
        if narrow.size == 0:
            return np.array([], dtype=np.float32)

        envelope = np.abs(narrow).astype(np.float64)
        envelope -= np.mean(envelope)

        audio = _boxcar_decimate_real(envelope, audio_decim)
        if audio.size == 0:
            return np.array([], dtype=np.float32)

        rms = float(np.sqrt(np.mean(audio * audio)))
        if rms > 1e-9:
            desired = self._target_rms / rms
            if desired < self.agc_gain:
                self.agc_gain = 0.3 * self.agc_gain + 0.7 * desired
            else:
                self.agc_gain = 0.97 * self.agc_gain + 0.03 * desired
            self.agc_gain = float(np.clip(self.agc_gain, self._agc_min, self._agc_max))

        out = np.clip(audio * self.agc_gain, -1.0, 1.0)
        return out.astype(np.float32)


_default_demod = AMDemodulator()


def demod_am(
    iq: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
    audio_rate: int = AIRBAND_AUDIO_RATE,
    *,
    demod: AMDemodulator | None = None,
) -> np.ndarray:
    """Convert complex IQ to mono PCM suitable for squelch and speech STT."""
    engine = _default_demod if demod is None else demod
    return engine.demod(iq, sample_rate=sample_rate, audio_rate=audio_rate)

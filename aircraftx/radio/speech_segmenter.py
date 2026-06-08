"""Energy-based squelch and speech segmentation for airband audio."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from aircraftx.config import AIRBAND_AUDIO_RATE
from aircraftx.radio.squelch import SquelchGate


@dataclass
class SpeechSegmenter:
    """Split a PCM stream into completed speech segments."""

    squelch: SquelchGate = field(default_factory=SquelchGate)
    sample_rate: int = AIRBAND_AUDIO_RATE
    min_speech_sec: float = 0.35
    hang_sec: float = 0.55
    max_segment_sec: float = 30.0
    _in_speech: bool = field(default=False, init=False)
    _segment: List[np.ndarray] = field(default_factory=list, init=False)
    _segment_samples: int = field(default=0, init=False)
    _silence_samples: int = field(default=0, init=False)

    def feed(self, audio: np.ndarray) -> List[np.ndarray]:
        if audio.size == 0:
            return []

        completed: List[np.ndarray] = []
        min_speech = int(self.min_speech_sec * self.sample_rate)
        hang = int(self.hang_sec * self.sample_rate)
        max_segment = int(self.max_segment_sec * self.sample_rate)

        if self.squelch.gate_open:
            if not self._in_speech:
                self._in_speech = True
                self._segment = []
                self._segment_samples = 0
            self._segment.append(audio.copy())
            self._segment_samples += audio.size
            self._silence_samples = 0
            if self._segment_samples >= max_segment:
                completed.append(self._flush())
        elif self._in_speech:
            self._segment.append(audio.copy())
            self._segment_samples += audio.size
            self._silence_samples += audio.size
            if self._silence_samples >= hang:
                if self._segment_samples >= min_speech:
                    completed.append(self._flush())
                else:
                    self._reset()

        return completed

    def _flush(self) -> np.ndarray:
        audio = np.concatenate(self._segment) if self._segment else np.array([])
        self._reset()
        return audio

    def _reset(self) -> None:
        self._in_speech = False
        self._segment = []
        self._segment_samples = 0
        self._silence_samples = 0

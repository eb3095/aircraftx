"""Optional local speech-to-text for airband voice segments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

import numpy as np

from aircraftx.config import AIRBAND_AUDIO_RATE


class SpeechTranscriber(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def status(self) -> str: ...

    def transcribe(
        self, audio: np.ndarray, sample_rate: int = AIRBAND_AUDIO_RATE
    ) -> str: ...


@dataclass
class StubTranscriber:
    """Placeholder when faster-whisper is not installed."""

    @property
    def available(self) -> bool:
        return False

    @property
    def status(self) -> str:
        return "missing dependencies"

    def transcribe(
        self, audio: np.ndarray, sample_rate: int = AIRBAND_AUDIO_RATE
    ) -> str:
        return "[voice activity detected]"


class WhisperTranscriber:
    """Local faster-whisper transcription (CPU int8)."""

    def __init__(self, model_size: str = "base.en") -> None:
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self._model_size = model_size

    @property
    def available(self) -> bool:
        return True

    @property
    def status(self) -> str:
        return f"Whisper {self._model_size} (local)"

    def transcribe(
        self, audio: np.ndarray, sample_rate: int = AIRBAND_AUDIO_RATE
    ) -> str:
        if audio.size == 0:
            return ""
        segments, _ = self._model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=False,
            initial_prompt=(
                "Aviation radio. ATC tower approach departure clearance squawk "
                "runway contact frequency."
            ),
        )
        text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
        return text.strip()


def create_transcriber() -> SpeechTranscriber:
    try:
        return WhisperTranscriber()
    except Exception:
        return StubTranscriber()

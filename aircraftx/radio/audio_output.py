"""Live speaker playback for demodulated airband audio."""

from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from aircraftx.config import AIRBAND_AUDIO_RATE


class AudioOutput:
    """Gapless playback via a ring buffer and PortAudio callback."""

    _BLOCK = 1024
    _MAX_BUFFER_SEC = 0.35

    def __init__(self, sample_rate: int = AIRBAND_AUDIO_RATE) -> None:
        self._sample_rate = sample_rate
        self._buf = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()
        self._stream = None
        self.available = False
        self._shutdown = False
        self._ready = threading.Event()
        threading.Thread(
            target=self._start,
            name="aircraftx-audio",
            daemon=True,
        ).start()

    def _start(self) -> None:
        try:
            import sounddevice as sd
        except ImportError:
            self._ready.set()
            return

        max_samples = int(self._sample_rate * self._MAX_BUFFER_SEC)

        def callback(
            outdata: np.ndarray,
            frames: int,
            _time_info: object,
            _status: object,
        ) -> None:
            with self._lock:
                if self._buf.size >= frames:
                    outdata[:, 0] = self._buf[:frames]
                    self._buf = self._buf[frames:]
                elif self._buf.size > 0:
                    n = self._buf.size
                    outdata[:n, 0] = self._buf
                    outdata[n:, 0] = 0.0
                    self._buf = np.zeros(0, dtype=np.float32)
                else:
                    outdata.fill(0.0)

        try:
            if self._shutdown:
                return
            stream = sd.OutputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self._BLOCK,
                callback=callback,
            )
            stream.start()
            if self._shutdown:
                stream.stop()
                stream.close()
                return
            self._stream = stream
            self.available = True
        except Exception:
            self._stream = None
            self.available = False
        finally:
            self._ready.set()

    def write(self, pcm: np.ndarray) -> None:
        if not self.available or pcm.size == 0:
            return
        samples = pcm.astype(np.float32, copy=False)
        max_samples = int(self._sample_rate * self._MAX_BUFFER_SEC)
        with self._lock:
            self._buf = np.concatenate([self._buf, samples])
            if self._buf.size > max_samples:
                self._buf = self._buf[-max_samples:]

    def shutdown(self) -> None:
        self._shutdown = True
        self._ready.wait(timeout=2.0)
        stream: Optional[object] = self._stream
        if stream is not None:
            stream.stop()
            stream.close()
            self._stream = None
        self.available = False

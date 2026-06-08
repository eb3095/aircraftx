"""HackRF One IQ capture via hackrf_transfer."""

from __future__ import annotations

import os
import select
import shutil
import subprocess
from typing import Optional

from aircraftx.config import (
    CHUNK_SAMPLES,
    FREQ_HZ,
    HACKRF_BINARY_PATHS,
    SAMPLE_RATE,
    RadioConfig,
)


class HackRFReceiver:
    def __init__(
        self,
        config: RadioConfig,
        *,
        freq_hz: int = FREQ_HZ,
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        self._config = config
        self._freq_hz = freq_hz
        self._sample_rate = sample_rate
        self._proc: Optional[subprocess.Popen[bytes]] = None

    @staticmethod
    def find_binary() -> Optional[str]:
        for candidate in HACKRF_BINARY_PATHS:
            path = shutil.which(candidate) if "/" not in candidate else candidate
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        return None

    def start(self) -> None:
        hackrf = self.find_binary()
        if not hackrf:
            raise RuntimeError(
                "hackrf_transfer not found. Install with: brew install hackrf"
            )

        cmd = [
            hackrf,
            "-r",
            "-",
            "-f",
            str(self._freq_hz),
            "-s",
            str(self._sample_rate),
            "-l",
            str(self._config.lna_gain),
            "-g",
            str(self._config.vga_gain),
            "-a",
            "1" if self._config.amp_enable else "0",
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

    def read_chunk(self, timeout: float = 0.05) -> bytes:
        if not self._proc or not self._proc.stdout:
            return b""
        fd = self._proc.stdout.fileno()
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return b""
        return os.read(fd, CHUNK_SAMPLES * 2)

    def set_frequency(self, freq_hz: int) -> None:
        """Retune the receiver (restarts hackrf_transfer if already running)."""
        if freq_hz == self._freq_hz:
            return
        running = self._proc is not None
        if running:
            self.stop()
        self._freq_hz = freq_hz
        if running:
            self.start()

    def stop(self) -> None:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    @property
    def freq_hz(self) -> int:
        return self._freq_hz

    @property
    def exited(self) -> bool:
        return self._proc is not None and self._proc.poll() is not None

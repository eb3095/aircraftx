"""RTL-SDR IQ capture via rtl_sdr."""

from __future__ import annotations

import os
import select
import shutil
import subprocess
from typing import Optional

from aircraftx.radio.process_util import stop_subprocess
from aircraftx.config import (
    CHUNK_SAMPLES,
    FREQ_HZ,
    RTL_SDR_BINARY_PATHS,
    SAMPLE_RATE,
    RadioConfig,
)


class RtlSdrReceiver:
    def __init__(
        self,
        config: RadioConfig,
        *,
        freq_hz: int = FREQ_HZ,
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        self._config = config
        self._freq_hz = int(freq_hz)
        self._sample_rate = int(sample_rate)
        self._proc: Optional[subprocess.Popen[bytes]] = None

    @staticmethod
    def find_binary() -> Optional[str]:
        for candidate in RTL_SDR_BINARY_PATHS:
            path = shutil.which(candidate) if "/" not in candidate else candidate
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        return None

    def start(self) -> None:
        rtl_sdr = self.find_binary()
        if not rtl_sdr:
            raise RuntimeError("rtl_sdr not found. Install with: brew install rtl-sdr")
        cmd = [
            rtl_sdr,
            "-f",
            str(self._freq_hz),
            "-s",
            str(self._sample_rate),
            "-g",
            str(self._config.tuner_gain),
            "-p",
            str(self._config.ppm_error),
            "-",
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
        if int(freq_hz) == self._freq_hz:
            return
        running = self._proc is not None
        if running:
            self.stop()
        self._freq_hz = int(freq_hz)
        if running:
            self.start()

    def stop(self, *, fast: bool = False) -> None:
        if self._proc:
            stop_subprocess(self._proc, fast=fast, prefer_sigint=not fast)
            self._proc = None

    @property
    def freq_hz(self) -> int:
        return self._freq_hz

    @property
    def exited(self) -> bool:
        return self._proc is not None and self._proc.poll() is not None

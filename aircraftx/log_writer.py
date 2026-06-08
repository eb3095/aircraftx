"""Append-only session logs under ~/.aircraftx/logs/."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TextIO

from aircraftx.acars.decoder import AcarsMessage


def default_log_dir() -> Path:
    override = os.environ.get("AIRCRAFTX_LOG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".aircraftx" / "logs"


LOG_DIR = default_log_dir()


def mhz_log_name(prefix: str, freq_mhz: float) -> str:
    """Build a log stem like radio_131.550 or acars_118.500."""
    return f"{prefix}_{freq_mhz:.3f}"


class LogWriter:
    """Thread-safe append-only writer for AircraftX dashboard logs."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self._dir = log_dir or default_log_dir()
        self._files: dict[str, TextIO] = {}
        self._lock = threading.Lock()

    @property
    def log_dir(self) -> Path:
        return self._dir

    def _append(self, stem: str, line: str) -> None:
        text = line.replace("\n", " ").replace("\r", " ").strip()
        if not text:
            return
        with self._lock:
            handle = self._files.get(stem)
            if handle is None:
                self._dir.mkdir(parents=True, exist_ok=True)
                path = self._dir / f"{stem}.log"
                handle = open(path, "a", encoding="utf-8", buffering=1)
                self._files[stem] = handle
            handle.write(text + "\n")
            handle.flush()

    def log_adsb(self, timestamp: str, icao: str, msg_type: str, summary: str) -> None:
        self._append("ads_b", f"{timestamp} {icao} {msg_type} {summary}")

    def log_mode_s(
        self, timestamp: str, icao: str, msg_type: str, summary: str
    ) -> None:
        self._append("mode_s", f"{timestamp} {icao} {msg_type} {summary}")

    def log_acars(self, freq_mhz: float, timestamp: str, message: AcarsMessage) -> None:
        parts = [timestamp, message.tail or "-", message.label]
        if message.flight:
            parts.append(message.flight)
        if message.msgno:
            parts.append(f"#{message.msgno}")
        if message.text:
            parts.append(message.text)
        self._append(mhz_log_name("acars", freq_mhz), " ".join(parts))

    def log_radio_transcript(self, freq_mhz: float, text: str) -> None:
        self._append(mhz_log_name("radio", freq_mhz), text)

    def close(self) -> None:
        with self._lock:
            for handle in self._files.values():
                handle.close()
            self._files.clear()

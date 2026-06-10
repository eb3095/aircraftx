"""SDR backend preference resolution with cross-backend fallback."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Literal

from aircraftx.config import (
    HACKRF_BINARY_PATHS,
    RTL_SDR_BINARY_PATHS,
    SAMPLE_RATE,
)

HACKRF_INFO_PATHS = (
    "hackrf_info",
    "/opt/homebrew/bin/hackrf_info",
    "/usr/local/bin/hackrf_info",
)

NO_SDR_MSG = "No supported SDR detected. Connect a HackRF or RTL-SDR and retry."
ResolvedBackend = Literal["hackrf", "rtlsdr"]
_PROBE_FREQ_HZ = 100_000_000
_PROBE_SAMPLES = 32_000


def _find_binary(candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        path = shutil.which(candidate) if "/" not in candidate else candidate
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def normalize_backend(backend: str) -> str:
    value = (backend or "auto").strip().lower()
    if value in {"rtl", "rtlsdr", "rtl-sdr"}:
        return "rtlsdr"
    if value == "hackrf":
        return "hackrf"
    return "auto"


def hackrf_present() -> bool:
    if _find_binary(HACKRF_BINARY_PATHS) is None:
        return False
    info = _find_binary(HACKRF_INFO_PATHS)
    if info is None:
        return True
    try:
        result = subprocess.run(
            [info], capture_output=True, timeout=3, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def rtlsdr_present() -> bool:
    rtl = _find_binary(RTL_SDR_BINARY_PATHS)
    if not rtl:
        return False
    try:
        result = subprocess.run(
            [
                rtl,
                "-f",
                str(_PROBE_FREQ_HZ),
                "-s",
                str(SAMPLE_RATE),
                "-g",
                "20",
                "-n",
                str(_PROBE_SAMPLES),
                os.devnull,
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode == 0:
        return True
    text = (result.stderr + result.stdout).decode("utf-8", errors="replace").lower()
    return "no supported devices" not in text and "usb_claim_interface" not in text


def resolve_backend(preferred: str) -> ResolvedBackend:
    choice = normalize_backend(preferred)
    if choice == "rtlsdr":
        order: tuple[ResolvedBackend, ...] = ("rtlsdr", "hackrf")
    elif choice == "hackrf":
        order = ("hackrf", "rtlsdr")
    else:
        order = ("hackrf", "rtlsdr")
    for name in order:
        if name == "hackrf" and hackrf_present():
            return "hackrf"
        if name == "rtlsdr" and rtlsdr_present():
            return "rtlsdr"
    raise RuntimeError(NO_SDR_MSG)

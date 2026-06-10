"""Coordinated SIGINT handling with immediate resource cleanup."""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable


class ShutdownCoordinator:
    """Register exit hooks; first Ctrl+C runs them immediately."""

    def __init__(self) -> None:
        self.running = True
        self._callbacks: list[Callable[[], None]] = []
        self._lock = threading.Lock()
        self._ran = False
        self._force_exit = False

    def on_exit(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def install(self) -> None:
        signal.signal(signal.SIGINT, self._on_sigint)

    def _on_sigint(self, signum: int, _frame: object) -> None:
        if self._force_exit:
            raise SystemExit(128 + signum)
        self.running = False
        self._run_exit_hooks()
        self._force_exit = True

    def cleanup(self) -> None:
        self.running = False
        self._run_exit_hooks()

    def _run_exit_hooks(self) -> None:
        with self._lock:
            if self._ran:
                return
            self._ran = True
        for callback in reversed(self._callbacks):
            try:
                callback()
            except Exception:
                pass

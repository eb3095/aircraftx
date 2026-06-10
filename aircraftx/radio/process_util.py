"""Fast, reliable subprocess teardown for SDR and decoder pipelines."""

from __future__ import annotations

import signal
import subprocess
from typing import IO


def _close_pipe(pipe: IO[bytes] | None) -> None:
    if pipe is None:
        return
    try:
        pipe.close()
    except OSError:
        pass


def stop_subprocess(
    proc: subprocess.Popen[bytes] | None,
    *,
    fast: bool = False,
    prefer_sigint: bool = False,
) -> None:
    """Terminate a child process; escalate to kill if it does not exit promptly."""
    if proc is None or proc.poll() is not None:
        return

    _close_pipe(proc.stdin)
    _close_pipe(proc.stdout)
    _close_pipe(proc.stderr)

    graceful = 0.35 if fast else 1.5
    force = 0.25 if fast else 1.0

    if prefer_sigint:
        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=graceful)
            return
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass

    try:
        proc.terminate()
        proc.wait(timeout=force)
        return
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass

    try:
        proc.kill()
        proc.wait(timeout=force)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass

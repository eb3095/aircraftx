"""macOS discovery notification audio."""

from __future__ import annotations

import os
import subprocess
import sys

DISCOVERY_SOUNDS = (
    "/System/Library/Sounds/Ping.aiff",
    "/System/Library/Sounds/Glass.aiff",
    "/System/Library/Sounds/Pop.aiff",
)


class DiscoverySound:
    @staticmethod
    def play() -> None:
        for path in DISCOVERY_SOUNDS:
            if os.path.isfile(path):
                subprocess.Popen(
                    ["afplay", path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
        sys.stdout.write("\a")
        sys.stdout.flush()

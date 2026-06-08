"""In-memory state for a single tracked transponder."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, Set

from aircraftx.config import CONFIRM_WINDOW_SEC, PREFERRED_DF


@dataclass
class Aircraft:
    icao: str
    callsign: str = ""
    altitude_ft: Optional[int] = None
    speed_kts: Optional[float] = None
    heading_deg: Optional[float] = None
    vertical_rate_fpm: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    squawk: Optional[str] = None
    category: str = ""
    bds: str = ""
    message_count: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    seen_hex: Set[str] = field(default_factory=set)
    last_df: Optional[int] = None
    last_tc: Optional[int] = None
    last_adsb_df: Optional[int] = None
    last_adsb_tc: Optional[int] = None
    df17_count: int = 0
    hit_times: Deque[float] = field(default_factory=deque)

    def recent_hits(self, now: float, window: float = CONFIRM_WINDOW_SEC) -> int:
        while self.hit_times and now - self.hit_times[0] > window:
            self.hit_times.popleft()
        return len(self.hit_times)

    def has_adsb(self) -> bool:
        return self.df17_count > 0

    def is_confirmed(self, now: float, min_hits: int) -> bool:
        # Once ADS-B is seen, keep the track confirmed regardless of later Mode-S.
        if self.df17_count >= 1:
            return True
        # Mode S transponder replies (DF4/11/20/21) are often single-shot.
        if (
            self.last_df is not None
            and self.last_df not in PREFERRED_DF
            and self.message_count >= 1
        ):
            return True
        return self.recent_hits(now) >= min_hits

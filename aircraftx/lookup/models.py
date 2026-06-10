"""Cached aircraft enrichment from external APIs."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

LookupStatus = Literal["queued", "loading", "ready", "error"]


@dataclass
class AircraftEnrichment:
    icao: str
    status: LookupStatus = "queued"
    registration: str = ""
    manufacturer: str = ""
    aircraft_type: str = ""
    icao_type_code: str = ""
    operator: str = ""
    owner: str = ""
    flight: str = ""
    route: str = ""
    departure: str = ""
    destination: str = ""
    error: str = ""
    updated_at: float = field(default_factory=time.time)

"""Default airband channels stored in user config."""

from __future__ import annotations

from typing import Any, Dict, List

# JSON-serializable channel entries for ~/.config/aircraftx/config.json
DEFAULT_RADIO_CHANNELS: List[Dict[str, Any]] = [
    {
        "id": "121.500",
        "name": "Emergency (Guard)",
        "freq_mhz": 121.5,
        "description": "International distress, urgency, and safety (121.5 MHz)",
    },
    {
        "id": "121.600",
        "name": "Multicom",
        "freq_mhz": 121.6,
        "description": "Air-to-air / practice area / remote field ops",
    },
    {
        "id": "121.700",
        "name": "Multicom",
        "freq_mhz": 121.7,
        "description": "Air-to-air and non-towered field coordination",
    },
    {
        "id": "121.800",
        "name": "Multicom",
        "freq_mhz": 121.8,
        "description": "Air-to-air; common CTAF at non-towered airports",
    },
    {
        "id": "121.900",
        "name": "Tower (typical)",
        "freq_mhz": 121.9,
        "description": "Air traffic control tower — pattern, takeoff, landing",
    },
    {
        "id": "122.000",
        "name": "Tower / ATC",
        "freq_mhz": 122.0,
        "description": "Tower or ATC — airport-specific assignment",
    },
    {
        "id": "122.700",
        "name": "Unicom",
        "freq_mhz": 122.7,
        "description": "FBO / airport advisory (fuel, parking, advisories)",
    },
    {
        "id": "122.800",
        "name": "CTAF / Multicom",
        "freq_mhz": 122.8,
        "description": "Common traffic advisory frequency (non-towered)",
    },
    {
        "id": "122.900",
        "name": "Multicom",
        "freq_mhz": 122.9,
        "description": "Air-to-air and field operations",
    },
    {
        "id": "123.000",
        "name": "Flight Service / ATC",
        "freq_mhz": 123.0,
        "description": "FSS, clearance delivery, or ATC — varies by region",
    },
    {
        "id": "118.000",
        "name": "ATIS (low band)",
        "freq_mhz": 118.0,
        "description": "Automated weather/information — tune local ATIS freq",
    },
    {
        "id": "119.100",
        "name": "Approach / Departure",
        "freq_mhz": 119.1,
        "description": "TRACON radar vectors — example freq; check chart",
    },
    {
        "id": "124.350",
        "name": "Approach / Departure",
        "freq_mhz": 124.35,
        "description": "TRACON sector — example freq; check chart",
    },
    {
        "id": "128.250",
        "name": "Center (ARTCC)",
        "freq_mhz": 128.25,
        "description": "En-route air traffic control — sector-specific",
    },
    {
        "id": "135.100",
        "name": "Flight Service",
        "freq_mhz": 135.1,
        "description": "En-route flight service / weather briefing",
    },
]

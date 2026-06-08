"""Default VHF ACARS channels stored in user config."""

from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_ACARS_CHANNELS: List[Dict[str, Any]] = [
    {
        "id": "131.550",
        "name": "Primary",
        "freq_mhz": 131.55,
        "description": "Most common US ACARS",
    },
    {
        "id": "131.525",
        "name": "Secondary",
        "freq_mhz": 131.525,
        "description": "Busy metro corridors",
    },
    {
        "id": "131.725",
        "name": "Channel 3",
        "freq_mhz": 131.725,
        "description": "Alternate ACARS",
    },
    {
        "id": "131.825",
        "name": "Channel 4",
        "freq_mhz": 131.825,
        "description": "Alternate ACARS",
    },
    {
        "id": "130.025",
        "name": "Low band",
        "freq_mhz": 130.025,
        "description": "Western US / overwater",
    },
    {
        "id": "130.425",
        "name": "Low band 2",
        "freq_mhz": 130.425,
        "description": "Regional ACARS",
    },
    {
        "id": "130.450",
        "name": "Low band 3",
        "freq_mhz": 130.45,
        "description": "Regional ACARS",
    },
    {
        "id": "131.125",
        "name": "Mid band",
        "freq_mhz": 131.125,
        "description": "Supplemental ACARS",
    },
]

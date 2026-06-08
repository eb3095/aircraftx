"""ACARS channel model and config parsing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence

from aircraftx.acars.channel_defaults import DEFAULT_ACARS_CHANNELS


@dataclass(frozen=True)
class AcarsChannel:
    channel_id: str
    freq_mhz: float
    name: str
    description: str = ""

    @property
    def freq_hz(self) -> int:
        return int(round(self.freq_mhz * 1_000_000))


def acars_from_dict(data: Mapping[str, Any]) -> AcarsChannel:
    freq_mhz = float(data["freq_mhz"])
    channel_id = str(data.get("id") or f"{freq_mhz:.3f}")
    name = str(data.get("name") or channel_id)
    description = str(data.get("description") or name)
    return AcarsChannel(
        channel_id=channel_id,
        freq_mhz=freq_mhz,
        name=name,
        description=description,
    )


def parse_acars_channels(
    entries: Optional[Sequence[Mapping[str, Any]]],
) -> List[AcarsChannel]:
    source = DEFAULT_ACARS_CHANNELS if not entries else entries
    return [acars_from_dict(item) for item in source]

"""Airband channel model, config parsing, and startup channel list."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from aircraftx.radio.channel_defaults import DEFAULT_RADIO_CHANNELS


@dataclass(frozen=True)
class AirbandChannel:
    channel_id: str
    name: str
    freq_hz: int
    description: str

    @property
    def freq_mhz(self) -> float:
        return self.freq_hz / 1_000_000


def channel_from_dict(data: Mapping[str, Any]) -> AirbandChannel:
    """Parse one JSON config channel entry."""
    freq_mhz = float(data["freq_mhz"])
    channel_id = str(data.get("id") or f"{freq_mhz:.3f}")
    name = str(data.get("name") or channel_id)
    description = str(data.get("description") or name)
    freq_hz = int(round(freq_mhz * 1_000_000))
    return AirbandChannel(
        channel_id=channel_id,
        name=name,
        freq_hz=freq_hz,
        description=description,
    )


def channel_to_dict(channel: AirbandChannel) -> Dict[str, Any]:
    return {
        "id": channel.channel_id,
        "name": channel.name,
        "freq_mhz": round(channel.freq_mhz, 3),
        "description": channel.description,
    }


def parse_config_channels(
    entries: Optional[Sequence[Mapping[str, Any]]],
) -> List[AirbandChannel]:
    source = DEFAULT_RADIO_CHANNELS if not entries else entries
    return [channel_from_dict(item) for item in source]


def dedupe_channels(channels: Iterable[AirbandChannel]) -> List[AirbandChannel]:
    seen: set[int] = set()
    unique: List[AirbandChannel] = []
    for channel in channels:
        if channel.freq_hz in seen:
            continue
        seen.add(channel.freq_hz)
        unique.append(channel)
    return unique


def build_channel_sets(
    *,
    lat: Optional[float],
    lon: Optional[float],
    config_channels: Optional[Sequence[Mapping[str, Any]]],
    local_lookup: bool = True,
    local_radius_km: float = 80.0,
    local_max_airports: int = 8,
) -> tuple[List[AirbandChannel], List[AirbandChannel]]:
    """Return (local dynamic channels, basic config channels) separately."""
    basic = parse_config_channels(config_channels)
    local: List[AirbandChannel] = []

    if local_lookup and lat is not None and lon is not None:
        try:
            from aircraftx.radio.local_lookup import lookup_local_channels

            local = lookup_local_channels(
                lat,
                lon,
                radius_km=local_radius_km,
                max_airports=local_max_airports,
            )
        except Exception:
            local = []

    return dedupe_channels(local), basic


def build_channel_list(
    *,
    lat: Optional[float],
    lon: Optional[float],
    config_channels: Optional[Sequence[Mapping[str, Any]]],
    local_lookup: bool = True,
    local_radius_km: float = 80.0,
    local_max_airports: int = 8,
) -> List[AirbandChannel]:
    """Legacy merge — prefer build_channel_sets for separate local/basic lists."""
    local, basic = build_channel_sets(
        lat=lat,
        lon=lon,
        config_channels=config_channels,
        local_lookup=local_lookup,
        local_radius_km=local_radius_km,
        local_max_airports=local_max_airports,
    )
    return dedupe_channels([*local, *basic])


def channel_by_id(
    channel_id: str,
    channels: Sequence[AirbandChannel] | None = None,
) -> AirbandChannel | None:
    pool = COMMON_AIRBAND_CHANNELS if channels is None else channels
    for channel in pool:
        if channel.channel_id == channel_id:
            return channel
    return None


# Backward-compatible alias used in older imports/tests.
COMMON_AIRBAND_CHANNELS: List[AirbandChannel] = parse_config_channels(None)

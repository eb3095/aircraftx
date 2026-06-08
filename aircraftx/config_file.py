"""Persistent user configuration at ~/.config/aircraftx/config.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, List, Optional

from aircraftx.config import SnifferConfig
from aircraftx.radio.channel_defaults import DEFAULT_RADIO_CHANNELS
from aircraftx.radio.channels import build_channel_sets

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "aircraftx"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"


@dataclass
class UserConfig:
    """JSON-serializable settings consumed by the CLI and SnifferConfig."""

    lat: Optional[float] = None
    lon: Optional[float] = None
    indoor: bool = True
    lna: int = 32
    vga: int = 48
    amp_enable: bool = True
    sound_enabled: bool = True
    refresh_hz: float = 2.0
    show_banner: bool = True
    replay_file: Optional[str] = None
    radio_channels: Optional[List[dict[str, Any]]] = None
    radio_local_lookup: bool = True
    radio_local_radius_km: float = 80.0
    radio_local_max_airports: int = 8

    @classmethod
    def defaults(cls) -> UserConfig:
        return cls(radio_channels=[dict(ch) for ch in DEFAULT_RADIO_CHANNELS])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserConfig:
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_sniffer_config(self) -> SnifferConfig:
        local, basic = build_channel_sets(
            lat=self.lat,
            lon=self.lon,
            config_channels=self.radio_channels,
            local_lookup=self.radio_local_lookup,
            local_radius_km=self.radio_local_radius_km,
            local_max_airports=self.radio_local_max_airports,
        )
        return SnifferConfig.from_preset(
            indoor=self.indoor,
            lat=self.lat,
            lon=self.lon,
            lna=self.lna,
            vga=self.vga,
            amp_enable=self.amp_enable,
            refresh_hz=self.refresh_hz,
            sound_enabled=self.sound_enabled,
            radio_local_channels=local,
            radio_basic_channels=basic,
        )


class ConfigStore:
    """Load, save, and bootstrap the user config file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_CONFIG_PATH

    def ensure(self) -> UserConfig:
        if not self.path.exists():
            self.write(UserConfig.defaults())
        return self.load()

    def load(self) -> UserConfig:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Config must be a JSON object: {self.path}")
        return UserConfig.from_dict(raw)

    def write(self, config: UserConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(config.to_dict(), indent=2, sort_keys=True)
        self.path.write_text(payload + "\n", encoding="utf-8")

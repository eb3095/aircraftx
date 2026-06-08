from __future__ import annotations

import json
from pathlib import Path

from aircraftx.acars.channel_defaults import DEFAULT_ACARS_CHANNELS
from aircraftx.config_file import ConfigStore, UserConfig


def test_user_config_defaults():
    cfg = UserConfig.defaults()
    assert cfg.indoor is True
    assert cfg.lna == 32
    assert cfg.sound_enabled is True


def test_user_config_ignores_legacy_adsb_only_key():
    cfg = UserConfig.from_dict({"adsb_only": False, "lna": 28})
    assert cfg.lna == 28
    assert cfg.to_sniffer_config().adsb_only is True


def test_user_config_round_trip():
    cfg = UserConfig(lat=40.45, lon=-74.13, indoor=False, lna=24)
    restored = UserConfig.from_dict(cfg.to_dict())
    assert restored.lat == 40.45
    assert restored.lon == -74.13
    assert restored.indoor is False
    assert restored.lna == 24


def test_config_store_creates_default_file(tmp_path: Path):
    path = tmp_path / "aircraftx" / "config.json"
    store = ConfigStore(path)
    cfg = store.ensure()
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["indoor"] is True
    assert cfg.indoor is True


def test_config_store_load_existing(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"lna": 40, "vga": 50, "indoor": False}) + "\n")
    store = ConfigStore(path)
    cfg = store.load()
    assert cfg.lna == 40
    assert cfg.vga == 50
    assert cfg.indoor is False


def test_to_sniffer_config_includes_acars_channels():
    cfg = UserConfig(acars_channels=[DEFAULT_ACARS_CHANNELS[0]])
    sniff = cfg.to_sniffer_config()
    assert len(sniff.acars_channels) == 1
    assert sniff.acars_channels[0].channel_id == "131.550"


def test_to_sniffer_config_indoor_preset():
    cfg = UserConfig(indoor=True, lat=1.0, lon=2.0)
    sniff = cfg.to_sniffer_config()
    assert sniff.lat_ref == 1.0
    assert sniff.lon_ref == 2.0
    assert sniff.tracker.min_confirm_hits == 2
    assert sniff.demod.corr_threshold_sigma == 5.5

from __future__ import annotations

from aircraftx.app.cli import build_parser, resolve_config
from aircraftx.config_file import UserConfig


def test_cli_overrides_config_defaults():
    defaults = UserConfig(lna=32, vga=48, indoor=True)
    parser = build_parser(defaults)
    args = parser.parse_args(["--lna", "24", "--outdoor", "--all-mode-s"])
    cfg = resolve_config(args, defaults)
    assert cfg.radio.lna_gain == 24
    assert cfg.demod.corr_threshold_sigma == 8.0  # outdoor preset
    assert cfg.adsb_only is False


def test_cli_defaults_to_adsb_only():
    defaults = UserConfig()
    parser = build_parser(defaults)
    args = parser.parse_args([])
    cfg = resolve_config(args, defaults)
    assert cfg.adsb_only is True


def test_cli_uses_config_when_no_overrides():
    defaults = UserConfig(lna=40, vga=50, indoor=False, lat=10.0, lon=20.0)
    parser = build_parser(defaults)
    args = parser.parse_args([])
    cfg = resolve_config(args, defaults)
    assert cfg.radio.lna_gain == 40
    assert cfg.radio.vga_gain == 50
    assert cfg.lat_ref == 10.0
    assert cfg.lon_ref == 20.0

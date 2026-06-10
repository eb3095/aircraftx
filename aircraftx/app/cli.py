"""AircraftX command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aircraftx import __app_name__, __version__
from aircraftx.app.sniffer import AircraftXSniffer
from aircraftx.config import SnifferConfig
from aircraftx.config_file import DEFAULT_CONFIG_PATH, ConfigStore, UserConfig
from aircraftx.radio.backends import resolve_backend
from aircraftx.radio.channels import build_channel_sets

BANNER = r"""
   _   _                     __ _  __  __
  /_\ (_)_ __ ___ _ __ __ _ / _| |_\ \/ /
 //_\\| | '__/ __| '__/ _` | |_| __|\  / 
/  _  \ | | | (__| | | (_| |  _| |_ /  \ 
\_/ \_/_|_|  \___|_|  \__,_|_|  \__/_/\_\
                                         
"""


def build_parser(defaults: UserConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=__app_name__,
        description=f"{__app_name__} v{__version__} — ADS-B receiver for HackRF (macOS)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"Config file: {DEFAULT_CONFIG_PATH}\n"
            "CLI options override config values.\n"
            "Setup: brew install hackrf && make dev-install"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=f"Path to config JSON (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--file",
        default=defaults.replay_file,
        help="Replay raw HackRF IQ capture (int8 I/Q interleaved) instead of live RX",
    )
    parser.add_argument(
        "--lat",
        type=float,
        default=defaults.lat,
        help="Your latitude (helps decode CPR position with a single frame)",
    )
    parser.add_argument(
        "--lon",
        type=float,
        default=defaults.lon,
        help="Your longitude (helps decode CPR position with a single frame)",
    )
    indoor = parser.add_mutually_exclusive_group()
    indoor.add_argument(
        "--indoor",
        dest="indoor",
        action="store_true",
        help="Relaxed sensitivity for weak indoor signals",
    )
    indoor.add_argument(
        "--outdoor",
        dest="indoor",
        action="store_false",
        help="Outdoor preset (stricter demod / confirmation)",
    )
    parser.set_defaults(indoor=defaults.indoor)

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--adsb-only",
        dest="adsb_only",
        action="store_true",
        help="Track ADS-B (DF17/18) only (default)",
    )
    mode.add_argument(
        "--all-mode-s",
        dest="adsb_only",
        action="store_false",
        help="Include Mode-S radar replies (DF4/11/20/21)",
    )
    parser.set_defaults(adsb_only=True)

    parser.add_argument(
        "--backend",
        choices=["auto", "hackrf", "rtlsdr"],
        default=defaults.backend,
        help="SDR backend preference (falls back to the other device if unavailable)",
    )
    parser.add_argument(
        "--lna",
        type=int,
        default=defaults.lna,
        help="LNA gain 0-40 dB",
    )
    parser.add_argument(
        "--vga",
        type=int,
        default=defaults.vga,
        help="VGA gain 0-62 dB",
    )
    amp = parser.add_mutually_exclusive_group()
    amp.add_argument(
        "--amp",
        dest="amp_enable",
        action="store_true",
        help="Enable HackRF RF amplifier (+11 dB)",
    )
    amp.add_argument(
        "--no-amp",
        dest="amp_enable",
        action="store_false",
        help="Disable HackRF RF amplifier",
    )
    parser.set_defaults(amp_enable=defaults.amp_enable)

    sound = parser.add_mutually_exclusive_group()
    sound.add_argument(
        "--sound",
        dest="sound_enabled",
        action="store_true",
        help="Play sound on the first ADS-B frame from a new aircraft",
    )
    sound.add_argument(
        "--no-sound",
        dest="sound_enabled",
        action="store_false",
        help="Disable discovery notification sound",
    )
    parser.set_defaults(sound_enabled=defaults.sound_enabled)

    parser.add_argument(
        "--refresh",
        type=float,
        default=defaults.refresh_hz,
        help="Dashboard refresh rate in Hz",
    )
    banner = parser.add_mutually_exclusive_group()
    banner.add_argument(
        "--banner",
        dest="show_banner",
        action="store_true",
        help="Show ASCII banner on startup",
    )
    banner.add_argument(
        "--no-banner",
        dest="show_banner",
        action="store_false",
        help="Skip ASCII banner on startup",
    )
    parser.set_defaults(show_banner=defaults.show_banner)
    return parser


def resolve_config(args: argparse.Namespace, user: UserConfig) -> SnifferConfig:
    local, basic = build_channel_sets(
        lat=args.lat,
        lon=args.lon,
        config_channels=user.radio_channels,
        local_lookup=user.radio_local_lookup,
        local_radius_km=user.radio_local_radius_km,
        local_max_airports=user.radio_local_max_airports,
    )
    from aircraftx.acars.channels import parse_acars_channels

    acars = parse_acars_channels(user.acars_channels)
    return SnifferConfig.from_preset(
        indoor=args.indoor,
        lat=args.lat,
        lon=args.lon,
        adsb_only=args.adsb_only,
        lna=args.lna,
        vga=args.vga,
        amp_enable=args.amp_enable,
        backend=resolve_backend(args.backend),
        tuner_gain=user.tuner_gain,
        ppm_error=user.ppm_error,
        refresh_hz=args.refresh,
        sound_enabled=args.sound_enabled,
        radio_local_channels=local,
        radio_basic_channels=basic,
        acars_channels=acars,
    )


def main(argv: list[str] | None = None) -> None:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=Path, default=None)
    pre_args, remaining = pre_parser.parse_known_args(argv)

    store = ConfigStore(pre_args.config)
    user_defaults = store.ensure()

    parser = build_parser(user_defaults)
    args = parser.parse_args(remaining)
    # Re-bind config path if provided on the main parser too.
    if args.config is not None:
        store = ConfigStore(args.config)
        store.ensure()

    if args.show_banner:
        print(BANNER)

    user_cfg = store.load()
    config = resolve_config(args, user_cfg)
    sniffer = AircraftXSniffer(config)
    replay = args.file or user_defaults.replay_file
    if replay:
        sniffer.run_file(replay)
    else:
        sniffer.run_live()


if __name__ == "__main__":
    main(sys.argv[1:])

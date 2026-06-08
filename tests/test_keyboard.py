from __future__ import annotations

from unittest.mock import patch

from aircraftx.ui import keyboard
from aircraftx.ui.keyboard import (
    _decode_key,
    _take_first_key,
    _wait_for_esc_completion,
    drain_keys,
    poll_key,
    reset_pending,
)


def setup_function() -> None:
    reset_pending()


def test_decode_key_mode_switch():
    assert _decode_key("a") == "mode_all"
    assert _decode_key("A") == "mode_adsb"


def test_decode_key_brackets_and_slash():
    assert _decode_key("[") == "prev"
    assert _decode_key("]") == "next"
    assert _decode_key("/") == "next"
    assert _decode_key("?") == "prev"
    assert _decode_key("\x03") == "quit"


def test_decode_key_arrows():
    assert _decode_key("\x1b[D") == "prev"
    assert _decode_key("\x1b[C") == "next"
    assert _decode_key("\x1b[A") == "channel_up"
    assert _decode_key("\x1b[B") == "channel_down"
    assert _decode_key("\x1bOD") == "prev"
    assert _decode_key("\x1bOC") == "next"
    assert _decode_key("\x1b[1;5D") == "prev"
    assert _decode_key("\x1b[1;2C") == "next"


def test_decode_key_dashboard_switch():
    assert _decode_key("R") == "dashboard_radio"
    assert _decode_key("D") == "dashboard_adsb"
    assert _decode_key("L") == "channel_source_local"
    assert _decode_key("B") == "channel_source_basic"


def test_decode_key_volume():
    assert _decode_key("+") == "volume_up"
    assert _decode_key("=") == "volume_up"
    assert _decode_key("-") == "volume_down"


def test_take_first_key_leaves_remainder():
    key, rest = _take_first_key("\x1b[D\x1b[C")
    assert key == "\x1b[D"
    assert rest == "\x1b[C"


def test_take_first_key_holds_incomplete_escape():
    key, rest = _take_first_key("\x1b[")
    assert key == "\x1b["
    assert rest == ""


def test_poll_key_brackets():
    keyboard._pending = ""
    with patch("aircraftx.ui.keyboard.sys.stdin.isatty", return_value=True):
        with patch(
            "aircraftx.ui.keyboard.select.select", return_value=([object()], [], [])
        ):
            with patch("aircraftx.ui.keyboard._read_available", return_value="["):
                assert poll_key() == "prev"


def test_poll_key_arrow_right_buffered():
    keyboard._pending = ""
    with patch("aircraftx.ui.keyboard.sys.stdin.isatty", return_value=True):
        with patch(
            "aircraftx.ui.keyboard.select.select", return_value=([object()], [], [])
        ):
            with patch("aircraftx.ui.keyboard._read_available", return_value="\x1b[C"):
                assert poll_key() == "next"


def test_poll_key_split_escape_waits_for_completion():
    keyboard._pending = ""
    with patch("aircraftx.ui.keyboard.sys.stdin.isatty", return_value=True):
        with patch(
            "aircraftx.ui.keyboard.select.select", return_value=([object()], [], [])
        ):
            with patch("aircraftx.ui.keyboard._read_available", return_value="\x1b"):
                with patch(
                    "aircraftx.ui.keyboard._wait_for_esc_completion",
                    return_value="\x1b[D",
                ):
                    assert poll_key() == "prev"


def test_drain_keys_multiple():
    keyboard._pending = ""
    with patch("aircraftx.ui.keyboard.sys.stdin.isatty", return_value=True):
        with patch(
            "aircraftx.ui.keyboard.select.select",
            side_effect=[([object()], [], []), ([], [], [])],
        ):
            with patch(
                "aircraftx.ui.keyboard._read_available",
                side_effect=["\x1b[D", ""],
            ):
                assert drain_keys() == ["prev"]


def test_wait_for_esc_completion():
    with patch("aircraftx.ui.keyboard.sys.stdin.fileno", return_value=0):
        with patch("aircraftx.ui.keyboard.select.select") as sel:
            sel.side_effect = [
                ([keyboard.sys.stdin], [], []),
                ([], [], []),
            ]
            with patch("aircraftx.ui.keyboard.os.read", return_value=b"[D"):
                assert _wait_for_esc_completion("\x1b") == "\x1b[D"

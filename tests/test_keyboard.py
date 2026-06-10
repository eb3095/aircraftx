from aircraftx.ui.keyboard import _decode_key


def test_lone_esc_decodes_to_deselect():
    assert _decode_key("\x1b") == "deselect"


def test_arrow_up_decodes_to_select_up():
    assert _decode_key("\x1b[A") == "channel_up"


def test_arrow_down_decodes_to_select_down():
    assert _decode_key("\x1b[B") == "channel_down"

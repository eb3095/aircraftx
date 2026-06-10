from aircraftx.ui.keyboard import _decode_key


def test_lone_esc_decodes_to_deselect():
    assert _decode_key("\x1b") == "deselect"


def test_arrow_up_decodes_to_select_up():
    assert _decode_key("\x1b[A") == "channel_up"


def test_m_decodes_to_toggle_map():
    assert _decode_key("M") == "toggle_map"
    assert _decode_key("m") == "toggle_map"


def test_map_close_invokes_callback():
    from aircraftx.ui.map_window import MapWindowController

    called: list[bool] = []
    controller = MapWindowController()
    controller.set_on_close(lambda: called.append(True))
    controller._open = True
    controller.close()
    assert called == [True]
    assert not controller.is_open()

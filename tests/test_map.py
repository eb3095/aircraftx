from __future__ import annotations

from aircraftx.ui.map_window import (
    MapAircraftView,
    PositionTrailStore,
    _PLANE_SPRITE_PATH,
    _format_hud,
    _get_plane_sprite_north,
    _view_signature,
    build_map_view,
    heading_cone_points,
)


def test_trail_store_dedupes_same_point():
    store = PositionTrailStore(maxlen=8)
    store.record("abc123", 40.0, -74.0)
    store.record("abc123", 40.0, -74.0)
    store.record("ABC123", 40.1, -74.1)
    assert store.trail("abc123") == [(40.0, -74.0), (40.1, -74.1)]


def test_trail_trim_drops_stale():
    store = PositionTrailStore(maxlen=8)
    store.record("KEEP01", 1.0, 2.0)
    store.record("DROP01", 3.0, 4.0)
    store.trim({"KEEP01"})
    assert store.trail("KEEP01")
    assert store.trail("DROP01") == []


def test_build_map_view_resolves_airports():
    cache = {"KJFK": (40.6413, -73.7781), "KLAX": (33.9416, -118.4085)}

    def coords(code: str):
        return cache.get(code.upper())

    view = build_map_view(
        aircraft_icao="A835AF",
        mode="latest",
        callsign="N628TS",
        latitude=40.5,
        longitude=-73.9,
        trail=[(40.4, -74.0), (40.5, -73.9)],
        departure="KJFK",
        destination="KLAX",
        airport_coords=coords,
    )
    assert view.departure_pos == (40.6413, -73.7781)
    assert view.destination_pos == (33.9416, -118.4085)
    assert len(view.trail) == 2


def test_single_point_trail_still_centers_map():
    view = MapAircraftView(
        icao="A835AF",
        latitude=40.5,
        longitude=-73.9,
        trail=[(40.5, -73.9)],
    )
    assert view.trail
    assert len(view.trail) < 2


def test_view_signature_ignores_trail_prefix():
    base = dict(
        icao="A835AF",
        latitude=40.5,
        longitude=-73.9,
        trail=[(40.4, -74.0), (40.5, -73.9)],
    )
    a = MapAircraftView(**base)
    b = MapAircraftView(**{**base, "trail": [(40.3, -74.1), (40.4, -74.0), (40.5, -73.9)]})
    assert _view_signature(a) != _view_signature(b)


def test_static_osm_map_zoom():
    from unittest.mock import MagicMock

    from aircraftx.ui.map_window import StaticOsmMap

    canvas = MagicMock()
    m = StaticOsmMap(canvas, 400, 300)
    m.set_center(40.0, -74.0, zoom=10)
    assert m.zoom_in()
    assert m.zoom == 11
    assert m.zoom_in()
    assert m.zoom == 12
    assert m.zoom_out()
    assert m.zoom == 11
    m.set_center(40.0, -74.0, zoom=18)
    assert not m.zoom_in()
    m.set_center(40.0, -74.0, zoom=3)
    assert not m.zoom_out()


def test_plane_sprite_asset():
    assert _PLANE_SPRITE_PATH.is_file()
    sprite = _get_plane_sprite_north()
    assert sprite.mode == "RGBA"
    assert sprite.size[0] == sprite.size[1]
    # Nose points up: opaque pixels extend further toward the top edge.
    width, height = sprite.size
    mid = width // 2
    top_band = sum(
        1 for y in range(height // 4) if sprite.getpixel((mid, y))[3] > 128
    )
    bottom_band = sum(
        1
        for y in range(height * 3 // 4, height)
        if sprite.getpixel((mid, y))[3] > 128
    )
    assert top_band > bottom_band
    assert sprite.getpixel((mid, height // 8))[:3] == (220, 38, 38)


def test_format_hud_includes_flight_data():
    view = MapAircraftView(
        icao="A835AF",
        mode="selected",
        callsign="N628TS",
        registration="N628TS",
        altitude_ft=41000,
        speed_kts=450,
        heading_deg=270,
        latitude=40.5,
        longitude=-73.9,
        route="KJFK-KLAX",
    )
    text = _format_hud(view)
    assert "A835AF" in text
    assert "selected" in text
    assert "N628TS" in text
    assert "41,000" in text
    assert "450" in text
    assert "270" in text
    assert "KJFK-KLAX" in text


def test_heading_cone_points_wedge():
    cone = heading_cone_points(40.0, -74.0, 0, half_angle_deg=15, length_nm=10)
    assert len(cone) == 3
    assert cone[0] == (40.0, -74.0)
    assert cone[1][0] > cone[0][0]
    assert cone[2][0] > cone[0][0]


def test_format_hud_legend_explains_track_and_route():
    view = MapAircraftView(
        icao="A835AF",
        latitude=40.5,
        longitude=-73.9,
        trail=[(40.4, -74.0), (40.5, -73.9)],
        departure="KJFK",
        destination="KLAX",
        departure_pos=(40.6413, -73.7781),
        destination_pos=(33.9416, -118.4085),
    )
    text = _format_hud(view)
    assert "recent track" in text
    assert "filed route" in text


def test_format_hud_legend_includes_heading_wedge():
    view = MapAircraftView(
        icao="A835AF",
        latitude=40.5,
        longitude=-73.9,
        heading_deg=270,
    )
    assert "heading" in _format_hud(view)


def test_map_follows_aircraft_position():
    from unittest.mock import MagicMock

    from aircraftx.ui.map_window import MapWindowController

    ctrl = MapWindowController()
    ctrl._map = MagicMock()
    ctrl._map.zoom = 12
    ctrl._hud = MagicMock()
    ctrl._hud_primary = MagicMock()
    ctrl._hud_stats = MagicMock()
    ctrl._hud_legend = MagicMock()

    first = MapAircraftView(icao="ABC123", latitude=40.0, longitude=-74.0)
    ctrl._apply_view(first)
    ctrl._map.set_center.assert_called_once_with(40.0, -74.0, zoom=10)

    ctrl._map.reset_mock()
    moved = MapAircraftView(icao="ABC123", latitude=40.2, longitude=-73.8)
    ctrl._apply_view(moved)
    ctrl._map.set_center.assert_called_once_with(40.2, -73.8, zoom=12)

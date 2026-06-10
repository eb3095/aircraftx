"""Live map window for the focused ADS-B aircraft."""

from __future__ import annotations

import io
import math
import threading
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from aircraftx.config import (
    MAP_HEADING_CONE_HALF_ANGLE_DEG,
    MAP_HEADING_CONE_LENGTH_NM,
    MAP_TRAIL_MAX_POINTS,
)
from aircraftx.lookup import hexdb
from aircraftx.ui.keyboard import suppress_stdio

LatLon = Tuple[float, float]

_EARTH_RADIUS_NM = 3440.065
_TILE_SIZE = 256
_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
_TILE_USER_AGENT = (
    "AircraftX/1.0 (ADS-B map; +https://github.com/ericbenner/aircraftx)"
)
_TILE_TIMEOUT_SEC = 8.0
_DEFAULT_ZOOM = 10
_MIN_ZOOM = 3
_MAX_ZOOM = 18

_PLANE_SPRITE_PATH = Path(__file__).resolve().parent / "assets" / "airplane_top.png"
_PLANE_SPRITE_FILL = (220, 38, 38, 255)
_plane_sprite_north: Optional[Any] = None


def _tint_plane_sprite(source: Any) -> Any:
    from PIL import Image

    rgba = source.convert("RGBA")
    _, _, _, alpha = rgba.split()
    tinted = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    fill = Image.new("RGBA", rgba.size, _PLANE_SPRITE_FILL)
    tinted.paste(fill, mask=alpha)
    return tinted


def _get_plane_sprite_north() -> Any:
    global _plane_sprite_north
    if _plane_sprite_north is None:
        from PIL import Image

        _plane_sprite_north = _tint_plane_sprite(Image.open(_PLANE_SPRITE_PATH))
    return _plane_sprite_north

_UI = {
    "bg": "#0f172a",
    "panel": "#1e293b",
    "text": "#f8fafc",
    "muted": "#94a3b8",
    "legend": "#64748b",
    "accent": "#38bdf8",
    "zoom_bg": "#ffffff",
    "zoom_border": "#cbd5e1",
    "zoom_fg": "#334155",
    "zoom_active": "#e2e8f0",
}


def _offset_nm(lat: float, lon: float, bearing_deg: float, distance_nm: float) -> LatLon:
    brng = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    ang_dist = distance_nm / _EARTH_RADIUS_NM
    lat2 = math.asin(
        math.sin(lat1) * math.cos(ang_dist)
        + math.cos(lat1) * math.sin(ang_dist) * math.cos(brng)
    )
    lon2 = lon1 + math.atan2(
        math.sin(brng) * math.sin(ang_dist) * math.cos(lat1),
        math.cos(ang_dist) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def heading_cone_points(
    lat: float,
    lon: float,
    heading_deg: float,
    *,
    half_angle_deg: float = MAP_HEADING_CONE_HALF_ANGLE_DEG,
    length_nm: float = MAP_HEADING_CONE_LENGTH_NM,
) -> List[LatLon]:
    """Wedge polygon: aircraft position plus two points at heading ± half_angle."""
    heading = heading_deg % 360
    left = _offset_nm(lat, lon, heading - half_angle_deg, length_nm)
    right = _offset_nm(lat, lon, heading + half_angle_deg, length_nm)
    return [(lat, lon), left, right]


def _latlon_to_world_px(lat: float, lon: float, zoom: int) -> Tuple[float, float]:
    scale = _TILE_SIZE * (2**zoom)
    x = (lon + 180.0) / 360.0 * scale
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return x, y


@dataclass
class MapAircraftView:
    icao: str
    mode: str = "latest"
    callsign: str = ""
    registration: str = ""
    altitude_ft: Optional[int] = None
    speed_kts: Optional[float] = None
    heading_deg: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    trail: List[LatLon] = field(default_factory=list)
    route: str = ""
    departure: str = ""
    destination: str = ""
    departure_pos: Optional[LatLon] = None
    destination_pos: Optional[LatLon] = None


def _view_signature(view: MapAircraftView) -> tuple:
    trail_tail = tuple(view.trail[-4:]) if view.trail else ()
    return (
        view.icao,
        view.mode,
        view.callsign,
        view.registration,
        view.altitude_ft,
        round(view.speed_kts or -1, 1),
        round(view.heading_deg or -1, 1),
        round(view.latitude or 0, 4),
        round(view.longitude or 0, 4),
        view.departure,
        view.destination,
        view.departure_pos,
        view.destination_pos,
        trail_tail,
    )


class PositionTrailStore:
    """Recent positions per ICAO for map track lines."""

    def __init__(self, maxlen: int = MAP_TRAIL_MAX_POINTS) -> None:
        self._maxlen = maxlen
        self._trails: Dict[str, Deque[LatLon]] = {}

    def record(self, icao: str, lat: float, lon: float) -> None:
        key = icao.strip().upper()
        trail = self._trails.get(key)
        if trail is None:
            trail = deque(maxlen=self._maxlen)
            self._trails[key] = trail
        point = (lat, lon)
        if trail and trail[-1] == point:
            return
        trail.append(point)

    def trail(self, icao: str) -> List[LatLon]:
        key = icao.strip().upper()
        stored = self._trails.get(key)
        return list(stored) if stored else []

    def drop(self, icao: str) -> None:
        self._trails.pop(icao.strip().upper(), None)

    def trim(self, active: set[str]) -> None:
        active_norm = {i.strip().upper() for i in active}
        stale = [k for k in self._trails if k not in active_norm]
        for key in stale:
            del self._trails[key]


class StaticOsmMap:
    """OpenStreetMap tiles fetched directly — no tkintermapview mainloop required."""

    def __init__(self, canvas: Any, width: int, height: int) -> None:
        self._canvas = canvas
        self._width = max(width, 1)
        self._height = max(height, 1)
        self._zoom = _DEFAULT_ZOOM
        self._center_lat = 39.8283
        self._center_lon = -98.5795
        self._tile_cache: Dict[Tuple[int, int, int], Any] = {}
        self._pending: set[Tuple[int, int, int]] = set()
        self._lock = threading.Lock()
        self._photo: Any = None
        self._bg_item: Optional[int] = None
        self._overlay_items: list[int] = []
        self._image_refs: list[Any] = []
        self._status_item: Optional[int] = None

    @property
    def zoom(self) -> int:
        return self._zoom

    def resize(self, width: int, height: int) -> None:
        width = max(width, 1)
        height = max(height, 1)
        if width == self._width and height == self._height:
            return
        self._width = width
        self._height = height

    def set_center(self, lat: float, lon: float, *, zoom: Optional[int] = None) -> None:
        self._center_lat = lat
        self._center_lon = lon
        if zoom is not None:
            self._zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, zoom))

    def zoom_in(self) -> bool:
        if self._zoom >= _MAX_ZOOM:
            return False
        self._zoom += 1
        return True

    def zoom_out(self) -> bool:
        if self._zoom <= _MIN_ZOOM:
            return False
        self._zoom -= 1
        return True

    def latlon_to_canvas(self, lat: float, lon: float) -> Tuple[float, float]:
        cx, cy = _latlon_to_world_px(self._center_lat, self._center_lon, self._zoom)
        px, py = _latlon_to_world_px(lat, lon, self._zoom)
        return px - cx + self._width / 2, py - cy + self._height / 2

    def clear_overlays(self) -> None:
        for item in self._overlay_items:
            self._canvas.delete(item)
        self._overlay_items = []
        self._image_refs = []

    def _place_rgba_image(self, image: Any, x: int, y: int) -> None:
        from PIL import ImageTk

        photo = ImageTk.PhotoImage(image)
        self._image_refs.append(photo)
        item = self._canvas.create_image(x, y, image=photo, anchor="nw")
        self._overlay_items.append(item)

    def draw_line(
        self,
        points: List[LatLon],
        *,
        fill: str,
        width: int = 2,
        dash: Optional[Tuple[int, ...]] = None,
    ) -> None:
        if len(points) < 2:
            return
        coords: list[float] = []
        for lat, lon in points:
            x, y = self.latlon_to_canvas(lat, lon)
            coords.extend((x, y))
        kwargs: dict[str, Any] = {"fill": fill, "width": width}
        if dash:
            kwargs["dash"] = dash
        item = self._canvas.create_line(*coords, **kwargs)
        self._overlay_items.append(item)

    def draw_polygon(
        self,
        points: List[LatLon],
        *,
        fill: str,
        outline: str,
        width: int = 1,
        stipple: Optional[str] = None,
    ) -> None:
        if len(points) < 3:
            return
        coords: list[float] = []
        for lat, lon in points:
            x, y = self.latlon_to_canvas(lat, lon)
            coords.extend((x, y))
        kwargs: dict[str, Any] = {
            "fill": fill,
            "outline": outline,
            "width": width,
        }
        if stipple:
            kwargs["stipple"] = stipple
        item = self._canvas.create_polygon(*coords, **kwargs)
        self._overlay_items.append(item)

    def draw_heading_wedge(
        self,
        lat: float,
        lon: float,
        heading_deg: float,
    ) -> None:
        """Semi-transparent heading wedge (PIL RGBA — stipple does not work on macOS)."""
        from PIL import Image, ImageDraw

        wedge = heading_cone_points(lat, lon, heading_deg)
        canvas_pts = [self.latlon_to_canvas(*point) for point in wedge]
        xs = [point[0] for point in canvas_pts]
        ys = [point[1] for point in canvas_pts]
        pad = 4
        x0 = int(min(xs)) - pad
        y0 = int(min(ys)) - pad
        x1 = int(max(xs)) + pad
        y1 = int(max(ys)) + pad
        width = max(1, x1 - x0)
        height = max(1, y1 - y0)
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        local = [(x - x0, y - y0) for x, y in canvas_pts]
        draw.polygon(local, fill=(59, 130, 246, 50), outline=(37, 99, 235, 90))
        self._place_rgba_image(image, x0, y0)

    def draw_aircraft(
        self,
        lat: float,
        lon: float,
        *,
        heading_deg: Optional[float] = None,
        label: str = "",
    ) -> None:
        from PIL import Image

        heading = heading_deg if heading_deg is not None else 0.0
        scale = max(0.9, min(1.35, 0.72 + self._zoom * 0.06))
        icon_px = max(28, int(44 * scale))
        sprite = _get_plane_sprite_north()
        resized = sprite.resize((icon_px, icon_px), Image.Resampling.LANCZOS)
        rotated = resized.rotate(
            -heading,
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
        x, y = self.latlon_to_canvas(lat, lon)
        left = int(x - rotated.width / 2)
        top = int(y - rotated.height / 2)
        self._place_rgba_image(rotated, left, top)

        if label:
            ly = y - icon_px * 0.45
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                outline_text = self._canvas.create_text(
                    x + dx,
                    ly + dy,
                    text=label,
                    fill="#0f172a",
                    font=("Helvetica Neue", 10, "bold"),
                )
                self._overlay_items.append(outline_text)
            text = self._canvas.create_text(
                x,
                ly,
                text=label,
                fill="#f8fafc",
                font=("Helvetica Neue", 10, "bold"),
            )
            self._overlay_items.append(text)

    def draw_marker(
        self,
        lat: float,
        lon: float,
        *,
        label: str = "",
        fill: str = "deepskyblue",
        outline: str = "navy",
        radius: int = 7,
    ) -> None:
        x, y = self.latlon_to_canvas(lat, lon)
        item = self._canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=fill,
            outline=outline,
            width=2,
        )
        self._overlay_items.append(item)
        if label:
            text = self._canvas.create_text(
                x,
                y - radius - 8,
                text=label,
                fill="#f8fafc",
                font=("Helvetica", 10, "bold"),
            )
            self._overlay_items.append(text)

    def refresh(self) -> None:
        """Fetch missing tiles and repaint the basemap (call from main thread)."""
        from PIL import Image, ImageTk

        self._schedule_fetches()
        cx, cy = _latlon_to_world_px(self._center_lat, self._center_lon, self._zoom)
        min_tx, min_ty, max_tx, max_ty = self._visible_tile_range()
        n = 2**self._zoom

        composite = Image.new("RGB", (self._width, self._height), (220, 220, 220))
        loaded = 0
        needed = 0

        for tx in range(min_tx, max_tx):
            for ty in range(min_ty, max_ty):
                tx_w = tx % n
                if ty < 0 or ty >= n:
                    continue
                needed += 1
                key = (self._zoom, tx_w, ty)
                with self._lock:
                    tile = self._tile_cache.get(key)
                if tile is None:
                    continue
                loaded += 1
                dest_x = int(tx * _TILE_SIZE - (cx - self._width / 2))
                dest_y = int(ty * _TILE_SIZE - (cy - self._height / 2))
                composite.paste(tile, (dest_x, dest_y))

        self._photo = ImageTk.PhotoImage(composite)
        if self._bg_item is None:
            self._bg_item = self._canvas.create_image(
                0, 0, image=self._photo, anchor="nw"
            )
        else:
            self._canvas.itemconfig(self._bg_item, image=self._photo)
        self._canvas.tag_lower(self._bg_item)
        for item in self._overlay_items:
            self._canvas.tag_raise(item)

        status = ""
        if needed and loaded < needed:
            status = f"Loading map tiles… ({loaded}/{needed})"
        if self._status_item is None:
            self._status_item = self._canvas.create_text(
                12,
                12,
                anchor="nw",
                text=status,
                fill="#1e293b",
                font=("Helvetica", 11, "bold"),
            )
        else:
            self._canvas.itemconfig(self._status_item, text=status)
            self._canvas.tag_raise(self._status_item)

    def _visible_tile_range(self) -> Tuple[int, int, int, int]:
        cx, cy = _latlon_to_world_px(self._center_lat, self._center_lon, self._zoom)
        left = cx - self._width / 2
        top = cy - self._height / 2
        right = cx + self._width / 2
        bottom = cy + self._height / 2
        return (
            int(math.floor(left / _TILE_SIZE)),
            int(math.floor(top / _TILE_SIZE)),
            int(math.floor(right / _TILE_SIZE)) + 1,
            int(math.floor(bottom / _TILE_SIZE)) + 1,
        )

    def _schedule_fetches(self) -> None:
        min_tx, min_ty, max_tx, max_ty = self._visible_tile_range()
        n = 2**self._zoom
        for tx in range(min_tx, max_tx):
            for ty in range(min_ty, max_ty):
                tx_w = tx % n
                if ty < 0 or ty >= n:
                    continue
                key = (self._zoom, tx_w, ty)
                with self._lock:
                    if key in self._tile_cache or key in self._pending:
                        continue
                    self._pending.add(key)
                threading.Thread(
                    target=self._fetch_tile,
                    args=key,
                    daemon=True,
                ).start()

    def _fetch_tile(self, zoom: int, x: int, y: int) -> None:
        from PIL import Image

        key = (zoom, x, y)
        url = _TILE_URL.format(z=zoom, x=x, y=y)
        req = urllib.request.Request(url, headers={"User-Agent": _TILE_USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=_TILE_TIMEOUT_SEC) as resp:
                tile = Image.open(io.BytesIO(resp.read())).convert("RGB")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            tile = Image.new("RGB", (_TILE_SIZE, _TILE_SIZE), (190, 190, 190))
        with self._lock:
            self._tile_cache[key] = tile
            self._pending.discard(key)


class MapWindowController:
    """Main-thread tkinter map; pump() from the sniffer loop (required on macOS)."""

    def __init__(
        self,
        ref_lat: Optional[float] = None,
        ref_lon: Optional[float] = None,
    ) -> None:
        self._ref_lat = ref_lat
        self._ref_lon = ref_lon
        self._open = False
        self._import_error = False
        self._root: Any = None
        self._hud: Any = None
        self._hud_primary: Any = None
        self._hud_stats: Any = None
        self._hud_legend: Any = None
        self._canvas: Any = None
        self._map: Optional[StaticOsmMap] = None
        self._shown_icao: Optional[str] = None
        self._pending_view: Optional[MapAircraftView] = None
        self._airport_cache: Dict[str, Optional[LatLon]] = {}
        self._airport_pending: set[str] = set()
        self._map_center: Optional[LatLon] = None
        self._last_view_signature: Optional[tuple] = None
        self._on_close: Optional[Callable[[], None]] = None
        self._last_view: Optional[MapAircraftView] = None

    def set_on_close(self, callback: Optional[Callable[[], None]]) -> None:
        self._on_close = callback

    def is_open(self) -> bool:
        return self._open

    def toggle(self) -> bool:
        if self.is_open():
            self.close()
            return False
        self.open()
        return self.is_open()

    def open(self) -> None:
        if self._open:
            return
        if not self._create_window():
            return
        self._open = True

    def close(self) -> None:
        if not self._open and self._root is None:
            return
        was_open = self._open
        self._open = False
        self._pending_view = None
        self._shown_icao = None
        self._map_center = None
        self._last_view_signature = None
        self._last_view = None
        self._airport_pending.clear()
        if self._map is not None:
            self._map.clear_overlays()
        if self._root is not None:
            with suppress_stdio():
                try:
                    self._root.withdraw()
                    self._root.update_idletasks()
                    self._root.destroy()
                except Exception:  # noqa: BLE001 — Tcl may already be torn down
                    pass
        self._root = None
        self._hud = None
        self._hud_primary = None
        self._hud_stats = None
        self._hud_legend = None
        self._canvas = None
        self._map = None
        if was_open and self._on_close is not None:
            try:
                self._on_close()
            except Exception:  # noqa: BLE001
                pass

    def shutdown(self) -> None:
        self.close()

    def update(self, view: Optional[MapAircraftView]) -> None:
        if not self._open:
            return
        self._pending_view = view

    def pump(self) -> None:
        """Process pending map updates and tk events (call from the main thread)."""
        if not self._open or self._root is None:
            return
        try:
            if not self._root.winfo_exists():
                self.close()
                return
        except Exception:  # noqa: BLE001
            self.close()
            return
        if self._pending_view is not None:
            signature = _view_signature(self._pending_view)
            if signature != self._last_view_signature:
                self._apply_view(self._pending_view)
                self._last_view_signature = signature
            self._pending_view = None
        try:
            with suppress_stdio():
                if self._map is not None:
                    self._map.refresh()
                self._root.update_idletasks()
                self._root.update()
        except Exception:  # noqa: BLE001
            self.close()

    def airport_coords(self, code: str) -> Optional[LatLon]:
        key = code.strip().upper()
        if not key:
            return None
        if key in self._airport_cache:
            return self._airport_cache[key]
        if key not in self._airport_pending:
            self._airport_pending.add(key)
            threading.Thread(
                target=self._fetch_airport_coords,
                args=(key,),
                daemon=True,
            ).start()
        return None

    def _fetch_airport_coords(self, key: str) -> None:
        try:
            self._airport_cache[key] = hexdb.lookup_airport_coords(key)
        finally:
            self._airport_pending.discard(key)

    def _create_window(self) -> bool:
        if self._import_error:
            return False
        try:
            import tkinter as tk

            from PIL import Image  # noqa: F401 — required for map tiles
        except ImportError:
            self._import_error = True
            return False

        root = tk.Tk()
        root.title("AircraftX — Live Map")
        root.geometry("960x720")
        root.configure(bg=_UI["bg"])

        hud_outer = tk.Frame(root, bg=_UI["bg"])
        hud_outer.pack(side="bottom", fill="x")
        hud_inner = tk.Frame(hud_outer, bg=_UI["panel"], padx=16, pady=12)
        hud_inner.pack(fill="x")
        hud_primary = tk.Label(
            hud_inner,
            text="Waiting for aircraft…",
            anchor="w",
            justify="left",
            font=("Helvetica Neue", 14, "bold"),
            bg=_UI["panel"],
            fg=_UI["text"],
        )
        hud_primary.pack(fill="x")
        hud_stats = tk.Label(
            hud_inner,
            text="",
            anchor="w",
            justify="left",
            font=("Helvetica Neue", 11),
            bg=_UI["panel"],
            fg=_UI["muted"],
        )
        hud_stats.pack(fill="x", pady=(6, 0))
        hud_legend = tk.Label(
            hud_inner,
            text="",
            anchor="w",
            justify="left",
            font=("Helvetica Neue", 9),
            bg=_UI["panel"],
            fg=_UI["legend"],
        )
        hud_legend.pack(fill="x", pady=(8, 0))

        canvas = tk.Canvas(
            root,
            width=940,
            height=620,
            bg="#dcdcdc",
            highlightthickness=0,
        )
        canvas.pack(fill="both", expand=True)

        map_view = StaticOsmMap(canvas, 940, 620)
        if self._ref_lat is not None and self._ref_lon is not None:
            map_view.set_center(self._ref_lat, self._ref_lon, zoom=9)
            self._map_center = (self._ref_lat, self._ref_lon)
        else:
            map_view.set_center(39.8283, -98.5795, zoom=5)
            self._map_center = (39.8283, -98.5795)

        def on_resize(event: Any) -> None:
            if event.widget is canvas and event.width > 1 and event.height > 1:
                map_view.resize(event.width, event.height)

        canvas.bind("<Configure>", on_resize)
        root.protocol("WM_DELETE_WINDOW", self._on_user_close)

        controls = tk.Frame(
            canvas,
            bg=_UI["zoom_bg"],
            highlightbackground=_UI["zoom_border"],
            highlightthickness=1,
            padx=2,
            pady=2,
        )

        def _zoom_btn(text: str, command: Callable[[], None]) -> Any:
            return tk.Button(
                controls,
                text=text,
                width=3,
                height=1,
                font=("Helvetica Neue", 17),
                command=command,
                bg=_UI["zoom_bg"],
                fg=_UI["zoom_fg"],
                activebackground=_UI["zoom_active"],
                activeforeground=_UI["zoom_fg"],
                relief="flat",
                bd=0,
                highlightthickness=0,
                cursor="hand2",
            )

        _zoom_btn("+", self._on_zoom_in).pack(pady=(4, 1), padx=4)
        tk.Frame(controls, bg=_UI["zoom_border"], height=1).pack(fill="x", padx=6)
        _zoom_btn("−", self._on_zoom_out).pack(pady=(1, 4), padx=4)
        controls.place(x=14, y=14)

        self._root = root
        self._hud = hud_inner
        self._hud_primary = hud_primary
        self._hud_stats = hud_stats
        self._hud_legend = hud_legend
        self._canvas = canvas
        self._map = map_view
        return True

    def _on_user_close(self) -> None:
        self.close()

    def _on_zoom_in(self) -> None:
        if self._map is not None and self._map.zoom_in():
            self._redraw_after_zoom()

    def _on_zoom_out(self) -> None:
        if self._map is not None and self._map.zoom_out():
            self._redraw_after_zoom()

    def _redraw_after_zoom(self) -> None:
        if self._last_view is not None:
            self._last_view_signature = None
            self._apply_view(self._last_view)
        if self._open and self._root is not None and self._map is not None:
            try:
                with suppress_stdio():
                    self._map.refresh()
                    self._root.update_idletasks()
            except Exception:  # noqa: BLE001
                pass

    def _apply_view(self, view: MapAircraftView) -> None:
        if self._map is None or self._hud is None:
            return

        self._last_view = view
        self._map.clear_overlays()
        self._update_hud(view)

        center_lat = view.latitude
        center_lon = view.longitude
        if center_lat is None or center_lon is None:
            if view.trail:
                center_lat, center_lon = view.trail[-1]
            elif self._ref_lat is not None and self._ref_lon is not None:
                center_lat, center_lon = self._ref_lat, self._ref_lon

        if center_lat is not None and center_lon is not None:
            focus_changed = self._shown_icao != view.icao
            zoom = _DEFAULT_ZOOM if focus_changed else self._map.zoom
            self._map.set_center(center_lat, center_lon, zoom=zoom)
            self._map_center = (center_lat, center_lon)

        if len(view.trail) >= 2:
            self._map.draw_line(view.trail, fill="#2563EB", width=3)

        if view.departure_pos:
            self._map.draw_marker(
                view.departure_pos[0],
                view.departure_pos[1],
                label=f"DEP {view.departure}",
                fill="#22c55e",
                outline="#14532d",
            )

        if view.destination_pos:
            self._map.draw_marker(
                view.destination_pos[0],
                view.destination_pos[1],
                label=f"DEST {view.destination}",
                fill="#f97316",
                outline="#7c2d12",
            )

        if view.departure_pos and view.destination_pos:
            self._map.draw_line(
                [view.departure_pos, view.destination_pos],
                fill="#64748B",
                width=2,
                dash=(8, 6),
            )

        if view.latitude is not None and view.longitude is not None:
            if view.heading_deg is not None:
                self._map.draw_heading_wedge(
                    view.latitude,
                    view.longitude,
                    view.heading_deg,
                )

            label = view.callsign.strip() or view.registration or view.icao
            self._map.draw_aircraft(
                view.latitude,
                view.longitude,
                heading_deg=view.heading_deg,
                label=label,
            )

        self._shown_icao = view.icao

    def _update_hud(self, view: MapAircraftView) -> None:
        if self._hud_primary is None:
            return
        primary, stats, legend = _hud_text_parts(view)
        self._hud_primary.configure(text=primary)
        self._hud_stats.configure(text=stats)
        self._hud_legend.configure(text=legend)


def _hud_text_parts(view: MapAircraftView) -> Tuple[str, str, str]:
    mode = "selected" if view.mode == "selected" else "latest"
    title_bits = [view.icao]
    if view.callsign.strip():
        title_bits.insert(0, view.callsign.strip())
    elif view.registration:
        title_bits.insert(0, view.registration)
    primary = f"{' · '.join(title_bits)}  ·  {mode}"

    stats_bits: list[str] = []
    if view.registration and view.registration not in primary:
        stats_bits.append(f"Reg {view.registration}")
    if view.altitude_ft is not None:
        stats_bits.append(f"Alt {view.altitude_ft:,} ft")
    if view.speed_kts is not None:
        stats_bits.append(f"Spd {view.speed_kts:.0f} kt")
    if view.heading_deg is not None:
        stats_bits.append(f"Hdg {view.heading_deg:.0f}°")
    if view.route:
        stats_bits.append(f"Route {view.route}")
    elif view.departure or view.destination:
        stats_bits.append(f"{view.departure or '?'} → {view.destination or '?'}")
    if view.latitude is None or view.longitude is None:
        stats_bits.append("Position not available yet")
    stats = "   ·   ".join(stats_bits)

    legend_bits: list[str] = []
    if view.heading_deg is not None and view.latitude is not None:
        legend_bits.append("shaded wedge = heading")
    if len(view.trail) >= 2:
        legend_bits.append("blue line = recent track")
    if view.departure_pos and view.destination_pos:
        legend_bits.append("gray dashed = filed route")
    legend = "   ·   ".join(legend_bits)
    return primary, stats, legend


def _format_hud(view: MapAircraftView) -> str:
    primary, stats, legend = _hud_text_parts(view)
    lines = [primary, stats]
    if legend:
        lines.append(legend)
    return "\n".join(line for line in lines if line)


def build_map_view(
    *,
    aircraft_icao: str,
    mode: str,
    callsign: str = "",
    registration: str = "",
    altitude_ft: Optional[int] = None,
    speed_kts: Optional[float] = None,
    heading_deg: Optional[float] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    trail: Optional[List[LatLon]] = None,
    route: str = "",
    departure: str = "",
    destination: str = "",
    airport_coords: Callable[[str], Optional[LatLon]],
) -> MapAircraftView:
    dep_pos = airport_coords(departure) if departure else None
    dest_pos = airport_coords(destination) if destination else None
    return MapAircraftView(
        icao=aircraft_icao,
        mode=mode,
        callsign=callsign,
        registration=registration,
        altitude_ft=altitude_ft,
        speed_kts=speed_kts,
        heading_deg=heading_deg,
        latitude=latitude,
        longitude=longitude,
        trail=trail or [],
        route=route,
        departure=departure,
        destination=destination,
        departure_pos=dep_pos,
        destination_pos=dest_pos,
    )

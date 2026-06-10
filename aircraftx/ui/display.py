"""Rich terminal dashboard for AircraftX."""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Set

from rich import box
from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from aircraftx import __app_name__
from aircraftx.ui.bars import FullWidthBar
from aircraftx.config import (
    MAX_RECENT_MESSAGES_STORE,
    PREFERRED_DF,
    RECENT_MESSAGES_DISPLAY,
    RadioConfig,
    SnifferConfig,
)
from aircraftx.decode.labels import table_type_is_adsb, table_type_label
from aircraftx.decode.tracker import AircraftTracker
from aircraftx.models.aircraft import Aircraft
from aircraftx.ui.formatters import (
    fmt_altitude_ft,
    fmt_optional,
    fmt_speed_kt,
    message_summary,
)
from aircraftx.log_writer import LogWriter
from aircraftx.lookup.models import AircraftEnrichment
from aircraftx.lookup.service import AircraftLookupService
from aircraftx.ui.sounds import DiscoverySound

PAGE_SIZE = 12


def _dim_text(content: str) -> Text:
    """Dim only — no italic (Cursor highlights italic) and always close tags."""
    return Text.from_markup(f"[dim]{content}[/]")


@dataclass
class RecentMessage:
    timestamp: str
    icao: str
    msg_type: str
    summary: str
    is_new_aircraft: bool


class ConsoleDisplay:
    def __init__(
        self,
        config: SnifferConfig,
        log_writer: LogWriter | None = None,
        lookup: AircraftLookupService | None = None,
    ) -> None:
        self.console = Console()
        self.adsb_only = config.adsb_only
        self.sound_enabled = config.sound_enabled
        self._log = log_writer
        self._lookup = lookup
        self.recent_adsb: Deque[RecentMessage] = deque(maxlen=MAX_RECENT_MESSAGES_STORE)
        self.recent_mode_s: Deque[RecentMessage] = deque(
            maxlen=MAX_RECENT_MESSAGES_STORE
        )
        self.seen_icao: Set[str] = set()
        self.adsb_notified: Set[str] = set()
        self.page_index = 0
        self.newest_first = True
        self.selected_index: Optional[int] = None
        self.last_discovered_icao: Optional[str] = None
        self._adsb_lookup_icaos: Set[str] = set()

    def push_message(self, aircraft: Aircraft, now: float) -> None:
        is_new = aircraft.icao not in self.seen_icao
        self.seen_icao.add(aircraft.icao)
        is_adsb = aircraft.last_df in PREFERRED_DF
        entry = RecentMessage(
            timestamp=time.strftime("%H:%M:%S", time.localtime(now)),
            icao=aircraft.icao,
            msg_type=table_type_label(aircraft, adsb_table=is_adsb),
            summary=message_summary(aircraft),
            is_new_aircraft=is_new,
        )
        if is_adsb:
            self.recent_adsb.append(entry)
            if is_new:
                self.last_discovered_icao = aircraft.icao
            if self._lookup is not None:
                key = aircraft.icao.strip().upper()
                callsign = (aircraft.callsign or "").strip()
                if key not in self._adsb_lookup_icaos:
                    self._adsb_lookup_icaos.add(key)
                    self._lookup.enqueue_aircraft(aircraft.icao)
                if callsign:
                    self._lookup.maybe_route(aircraft.icao, callsign)
            self.maybe_play_adsb_discovery(aircraft)
            if self._log is not None:
                self._log.log_adsb(
                    entry.timestamp, entry.icao, entry.msg_type, entry.summary
                )
        else:
            self.recent_mode_s.append(entry)
            if self._log is not None:
                self._log.log_mode_s(
                    entry.timestamp, entry.icao, entry.msg_type, entry.summary
                )

    def maybe_play_adsb_discovery(self, aircraft: Aircraft) -> None:
        """Ping once per ICAO on the first ADS-B (DF17/18) frame, not on updates."""
        if not self.sound_enabled or aircraft.icao in self.adsb_notified:
            return
        self.adsb_notified.add(aircraft.icao)
        DiscoverySound.play()

    def _active_recent(self) -> Deque[RecentMessage]:
        return self.recent_adsb if self.adsb_only else self.recent_mode_s

    def handle_key(self, key: str, total_rows: int) -> None:
        pages = self._page_count(total_rows)
        if key == "prev":
            self.page_index = max(0, self.page_index - 1)
        elif key == "next":
            self.page_index = min(pages - 1, self.page_index + 1)
        elif key == "first":
            self.newest_first = False
            self.page_index = 0
            self.selected_index = None
        elif key == "last":
            self.newest_first = True
            self.page_index = 0
            self.selected_index = None
        elif key in ("select_up", "channel_up"):
            self._move_selection(total_rows, -1)
        elif key in ("select_down", "channel_down"):
            self._move_selection(total_rows, 1)
        elif key == "deselect":
            self.selected_index = None

    def _move_selection(self, total_rows: int, delta: int) -> None:
        if total_rows <= 0:
            self.selected_index = None
            return
        if self.selected_index is None:
            # First arrow press: ↓ starts at top row, ↑ at bottom row.
            self.selected_index = 0 if delta > 0 else total_rows - 1
        else:
            self.selected_index = (self.selected_index + delta) % total_rows
        self._sync_page_to_selection(total_rows)

    def _sync_page_to_selection(self, total_rows: int) -> None:
        if self.selected_index is None:
            return
        self.page_index = self.selected_index // PAGE_SIZE
        self.sync_page(total_rows)

    @property
    def _last_ordered_icaos(self) -> List[str]:
        return getattr(self, "_ordered_icao_cache", [])

    def _highlight_icao(self, ordered: List[Aircraft]) -> Optional[str]:
        if self.selected_index is None:
            return None
        if 0 <= self.selected_index < len(ordered):
            return ordered[self.selected_index].icao
        return None

    def _focus_icao(self, ordered: List[Aircraft]) -> Optional[str]:
        highlighted = self._highlight_icao(ordered)
        if highlighted is not None:
            return highlighted
        return self.last_discovered_icao

    def sync_page(self, total_rows: int) -> None:
        pages = self._page_count(total_rows)
        self.page_index = min(self.page_index, pages - 1)

    @staticmethod
    def _page_count(total_rows: int) -> int:
        return max(1, math.ceil(total_rows / PAGE_SIZE) if total_rows else 1)

    @staticmethod
    def _confirmed_adsb(tracker: AircraftTracker, now: float) -> List[Aircraft]:
        return [ac for ac in tracker.confirmed_aircraft(now) if ac.df17_count > 0]

    @staticmethod
    def _confirmed_mode_s(tracker: AircraftTracker, now: float) -> List[Aircraft]:
        return [ac for ac in tracker.confirmed_aircraft(now) if ac.df17_count == 0]

    def _visible_confirmed(
        self, tracker: AircraftTracker, now: float
    ) -> List[Aircraft]:
        if self.adsb_only:
            return self._confirmed_adsb(tracker, now)
        return self._confirmed_mode_s(tracker, now)

    def _ordered_aircraft(self, tracker: AircraftTracker, now: float) -> List[Aircraft]:
        rows = self._visible_confirmed(tracker, now)
        if self.newest_first:
            return sorted(rows, key=lambda ac: (-ac.first_seen, ac.icao))
        return sorted(rows, key=lambda ac: (ac.first_seen, ac.icao))

    def confirmed_count(self, tracker: AircraftTracker, now: float) -> int:
        return len(self._visible_confirmed(tracker, now))

    def render(
        self,
        tracker: AircraftTracker,
        now: float,
        radio: RadioConfig,
    ) -> Group:
        ordered = self._ordered_aircraft(tracker, now)
        self._ordered_icao_cache = [ac.icao for ac in ordered]
        self.sync_page(len(ordered))

        parts: List[RenderableType] = [
            self._header(self.adsb_only),
            self._status_line(tracker, now, radio),
            self._aircraft_table(ordered, now),
        ]
        if self.adsb_only:
            parts.append(self._enrichment_panel(ordered))
        parts.append(self._recent_panel())
        hint = self._hint_panel(tracker, now)
        if hint:
            parts.append(hint)
        parts.append(self._footer())
        return Group(*parts)

    def print_once(
        self, tracker: AircraftTracker, now: float, radio: RadioConfig
    ) -> None:
        self.console.print(self.render(tracker, now, radio))

    @staticmethod
    def _header(adsb_only: bool) -> FullWidthBar:
        mode = "ADS-B" if adsb_only else "Mode S"
        return FullWidthBar(f" {__app_name__} — 1090 MHz · {mode} ")

    def _status_line(
        self,
        tracker: AircraftTracker,
        now: float,
        radio: RadioConfig,
    ) -> Text:
        tracker.purge_stale(now)
        all_confirmed = tracker.confirmed_aircraft(now)
        mode_s_count = len(self._confirmed_mode_s(tracker, now))
        adsb_count = len(self._confirmed_adsb(tracker, now))
        pending = len(tracker.aircraft) - len(all_confirmed)
        text = Text()
        text.append("1090 MHz", style="bold cyan")
        text.append("  │  ")
        text.append(f"LNA {radio.lna_gain}", style="dim")
        text.append("  ")
        text.append(f"VGA {radio.vga_gain}", style="dim")
        text.append("  ")
        text.append(f"amp {'on' if radio.amp_enable else 'off'}", style="dim")
        text.append("  │  ")
        text.append(f"{mode_s_count} Mode-S", style="bold yellow")
        text.append("  │  ")
        text.append(f"{adsb_count} ADS-B", style="bold green")
        if tracker.df17_messages > adsb_count:
            text.append(f" ({tracker.df17_messages} fr)", style="dim green")
        text.append("  │  ")
        text.append(
            f"{pending} pending",
            style="yellow" if pending else "dim",
        )
        if self.adsb_only and self._lookup is not None:
            lookup_pending = self._lookup.pending_count()
            text.append("  │  ")
            text.append(
                f"{lookup_pending} lookup pending",
                style="yellow" if lookup_pending else "dim",
            )
        text.append("  │  ")
        text.append(f"{tracker.total_crc_ok} accepted", style="dim")
        if tracker.lat_ref is not None and tracker.lon_ref is not None:
            text.append("  │  ")
            text.append(
                f"ref {tracker.lat_ref:.3f}, {tracker.lon_ref:.3f}",
                style="dim",
            )
        return text

    def _aircraft_table(self, ordered: List[Aircraft], now: float) -> Table:
        total = len(ordered)
        pages = self._page_count(total)
        page = self.page_index
        start = page * PAGE_SIZE
        shown = ordered[start : start + PAGE_SIZE]
        list_label = "ADS-B" if self.adsb_only else "Mode-S"

        if total == 0:
            title = f"Confirmed {list_label}"
        else:
            end = min(start + len(shown), total)
            order_label = "newest first" if self.newest_first else "oldest first"
            title = (
                f"Confirmed {list_label} · {order_label} · "
                f"page {page + 1}/{pages} ({start + 1}–{end} of {total})"
            )

        table = Table(
            title=title,
            box=box.ROUNDED,
            header_style="bold magenta",
            border_style="blue",
            show_lines=False,
            expand=True,
        )
        table.add_column("ICAO", style="bold white", no_wrap=True)
        table.add_column("Type", no_wrap=True)
        table.add_column("Callsign", style="cyan")
        table.add_column("Alt (ft)", justify="right", style="yellow")
        table.add_column("Spd (kt)", justify="right", style="green")
        table.add_column("Hdg", justify="right")
        table.add_column("Lat", style="dim")
        table.add_column("Lon", style="dim")
        table.add_column("Sq", justify="center", style="red")
        table.add_column("N", justify="right", style="dim")
        table.add_column("Age", justify="right", style="dim")

        if not shown:
            table.add_row(
                "—", "—", "listening…", "—", "—", "—", "—", "—", "—", "—", "—"
            )
            return table

        highlight = self._highlight_icao(ordered) if self.adsb_only else None
        for ac in shown:
            is_adsb_row = table_type_is_adsb(ac, adsb_table=self.adsb_only)
            type_style = "bold green" if is_adsb_row else "yellow"
            row_style = "reverse" if highlight and ac.icao == highlight else None
            table.add_row(
                ac.icao,
                Text(table_type_label(ac, adsb_table=self.adsb_only), style=type_style),
                ac.callsign or "—",
                fmt_altitude_ft(ac.altitude_ft),
                fmt_speed_kt(ac.speed_kts),
                fmt_optional(ac.heading_deg, "°"),
                fmt_optional(ac.latitude, "", na="—"),
                fmt_optional(ac.longitude, "", na="—"),
                ac.squawk or "—",
                str(ac.message_count),
                f"{now - ac.last_seen:.0f}s",
                style=row_style,
            )
        return table

    def _enrichment_panel(self, ordered: List[Aircraft]) -> Panel:
        focus_icao = self._focus_icao(ordered)
        if not focus_icao:
            body: RenderableType = _dim_text("Waiting for new ADS-B aircraft…")
            title = "[bold]Aircraft Details[/bold]"
            return Panel(body, title=title, border_style="cyan", padding=(0, 1))

        enrichment = self._lookup.get(focus_icao) if self._lookup else None
        ac = next((a for a in ordered if a.icao == focus_icao), None)
        body = self._format_enrichment(focus_icao, enrichment, ac)
        if self.selected_index is not None:
            title = f"[bold]Aircraft Details[/bold] · {focus_icao} [dim](selected)[/]"
        else:
            title = f"[bold]Aircraft Details[/bold] · {focus_icao} [dim](latest)[/]"
        return Panel(body, title=title, border_style="cyan", padding=(0, 1))

    def _format_enrichment(
        self,
        icao: str,
        enrichment: Optional[AircraftEnrichment],
        aircraft: Optional[Aircraft],
    ) -> Text:
        text = Text()
        text.append("ICAO ", style="dim")
        text.append(icao, style="bold white")
        if aircraft and aircraft.callsign:
            text.append("  ")
            text.append("Callsign ", style="dim")
            text.append(aircraft.callsign.strip(), style="cyan")

        if enrichment is None:
            text.append("\n")
            text.append_text(_dim_text("Lookup queued…"))
            return text

        if enrichment.status in ("queued", "loading"):
            text.append("\n")
            detail = enrichment.error or "Lookup pending…"
            text.append_text(_dim_text(detail))
            return text

        if enrichment.status == "error":
            text.append("\n")
            text.append(enrichment.error or "Lookup failed", style="red")
            return text

        fields = [
            ("Registration", enrichment.registration),
            ("Type", enrichment.aircraft_type or enrichment.icao_type_code),
            ("Manufacturer", enrichment.manufacturer),
            ("Operator", enrichment.operator),
            ("Owner", enrichment.owner),
            ("Flight", enrichment.flight),
            ("Route", enrichment.route),
            ("Departure", enrichment.departure),
            ("Destination", enrichment.destination),
        ]
        shown = False
        for label, value in fields:
            if not value:
                continue
            shown = True
            text.append("\n")
            text.append(f"{label} ", style="dim")
            text.append(value, style="bold" if label == "Registration" else "")
        if not shown:
            text.append("\n")
            text.append_text(_dim_text("No enrichment data available."))
        return text

    def _format_recent_line(self, msg: RecentMessage, *, is_adsb: bool) -> Text:
        line = Text()
        line.append(f"{msg.timestamp}  ", style="dim")
        if msg.is_new_aircraft:
            line.append("NEW ", style="bold green")
        line.append(msg.icao, style="bold")
        line.append("  ")
        line.append(msg.msg_type, style="green" if is_adsb else "yellow")
        line.append("  ")
        line.append(msg.summary, style="cyan")
        return line

    def _recent_panel(self) -> Panel:
        recent = list(self._active_recent())[-RECENT_MESSAGES_DISPLAY:]
        is_adsb = self.adsb_only
        if not recent:
            body: RenderableType = _dim_text("Waiting for signals…")
        else:
            lines = [
                self._format_recent_line(msg, is_adsb=is_adsb)
                for msg in reversed(recent)
            ]
            body = Text("\n").join(lines)

        label = "ADS-B" if self.adsb_only else "Mode-S"
        return Panel(
            body,
            title=f"[bold]Last {RECENT_MESSAGES_DISPLAY} {label} Messages[/bold]",
            border_style="green",
            padding=(0, 1),
            style="none",
        )

    def _footer(self) -> RenderableType:
        text = Text()
        text.append("←", style="bold cyan")
        text.append(" ")
        text.append("→", style="bold cyan")
        text.append("  ")
        text.append("[", style="bold")
        text.append(" ")
        text.append("]", style="bold")
        text.append("  ")
        text.append("/", style="bold cyan")
        text.append(" pages", style="dim")
        text.append("  ·  ", style="dim")
        text.append("G", style="bold cyan")
        text.append(" latest", style="dim")
        text.append("  ·  ", style="dim")
        text.append("g", style="bold cyan")
        text.append(" oldest", style="dim")
        text.append("  ·  ", style="dim")
        text.append("a", style="bold cyan")
        text.append(" Mode-S", style="dim")
        text.append("  ·  ", style="dim")
        text.append("A", style="bold cyan")
        text.append(" ADS-B", style="dim")
        if self.adsb_only:
            text.append("  ·  ", style="dim")
            text.append("↑↓", style="bold cyan")
            text.append(" select", style="dim")
            text.append("  ·  ", style="dim")
            text.append("Esc", style="bold cyan")
            text.append(" latest", style="dim")
        text.append("  ·  ", style="dim")
        text.append("R", style="bold cyan")
        text.append(" radio", style="dim")
        text.append("  ·  ", style="dim")
        text.append("C", style="bold cyan")
        text.append(" ACARS", style="dim")
        if self.newest_first:
            text.append("  ·  ", style="dim")
            text.append("newest on page 1", style="italic green")
        text.append("  ·  ")
        text.append_text(_dim_text("Ctrl+C stop"))
        return Align.center(text)

    def _hint_panel(self, tracker: AircraftTracker, now: float) -> Optional[Panel]:
        visible = self._visible_confirmed(tracker, now)
        if len(visible) > 0:
            return None

        mode_s_count = len(self._confirmed_mode_s(tracker, now))
        adsb_count = len(self._confirmed_adsb(tracker, now))

        if self.adsb_only and mode_s_count > 0:
            hint = (
                f"[bold]{mode_s_count}[/bold] Mode-S transponder(s) on the status bar — "
                "radar replies, not ADS-B aircraft. Press [bold]a[/bold] "
                "to browse Mode-S."
            )
        elif not self.adsb_only and adsb_count > 0:
            hint = (
                f"[bold]{adsb_count}[/bold] ADS-B aircraft on the status bar. "
                "Press [bold]A[/bold] to browse ADS-B."
            )
        elif tracker.total_crc_ok == 0:
            if self.adsb_only:
                hint = (
                    "No ADS-B yet — antenna near a window, try "
                    "[bold]--indoor --lna 32 --vga 48[/bold]"
                )
            else:
                hint = (
                    "No Mode-S replies yet — antenna near a window, try "
                    "[bold]--indoor --lna 32 --vga 48[/bold]"
                )
        elif len(tracker.aircraft) > 0:
            if self.adsb_only:
                hint = (
                    f"Waiting for [bold]{tracker.settings.min_confirm_hits}[/bold] "
                    "repeat ADS-B messages from the same ICAO…"
                )
            else:
                hint = (
                    "Mode-S replies confirm on one hit; ADS-B confirms on "
                    "the first DF17/18 frame…"
                )
        else:
            hint = (
                f"Demodulated [bold]{tracker.total_messages}[/bold] candidate(s), "
                f"[bold]{tracker.total_crc_ok}[/bold] passed filters — keep listening."
            )
        return Panel(hint, border_style="yellow", padding=(0, 1), style="none")

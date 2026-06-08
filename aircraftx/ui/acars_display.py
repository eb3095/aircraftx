"""VHF ACARS monitor dashboard."""

from __future__ import annotations

from typing import List

from rich import box
from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from aircraftx import __app_name__
from aircraftx.acars.channels import AcarsChannel
from aircraftx.acars.monitor import AcarsLine, AcarsMonitor
from aircraftx.config import MAX_ACARS_MESSAGES, RadioConfig
from aircraftx.ui.bars import FullWidthBar
from aircraftx.ui.display import _dim_text


class AcarsDisplay:
    def __init__(self, monitor: AcarsMonitor, radio: RadioConfig) -> None:
        self.console = Console()
        self.monitor = monitor
        self.radio = radio

    def render(self) -> Group:
        channel = self.monitor.selected_channel()
        return Group(
            FullWidthBar(f" {__app_name__} — VHF ACARS Monitor "),
            self._status_line(channel),
            self._channel_panel(),
            self._message_panel(channel),
            self._footer(),
        )

    def _status_line(self, channel: AcarsChannel) -> Text:
        text = Text()
        text.append(f"{channel.freq_mhz:.3f} MHz", style="bold cyan")
        text.append("  │  ")
        text.append(channel.name, style="bold yellow")
        text.append("  │  ")
        text.append(f"LNA {self.radio.lna_gain}", style="dim")
        text.append("  ")
        text.append(f"VGA {self.radio.vga_gain}", style="dim")
        text.append("  │  ")
        text.append(f"{self.monitor.total_messages} decoded", style="bold green")
        text.append("  │  ")
        lvl = self.monitor.last_level_db
        text.append(f"lvl {lvl:+.1f} dB", style="cyan" if lvl > -30 else "dim")
        return text

    def _channel_panel(self) -> Panel:
        table = Table(
            box=box.SIMPLE_HEAVY,
            show_header=True,
            header_style="bold",
            expand=True,
            padding=(0, 1),
        )
        table.add_column("", width=2, justify="center")
        table.add_column("MHz", width=9, justify="right")
        table.add_column("Name", width=14)
        table.add_column("Description", ratio=1)
        table.add_column("Msgs", width=5, justify="right")

        page_start = self.monitor.page_index * self.monitor.channel_page_size
        page_rows = self.monitor.page_channels()
        if not page_rows:
            table.add_row("", "-", "-", _dim_text("No channels"), "0")
        else:
            for offset, channel in enumerate(page_rows):
                idx = page_start + offset
                marker = ">" if idx == self.monitor.selected_index else ""
                row_style = (
                    "bold white on blue" if idx == self.monitor.selected_index else ""
                )
                count = len(self.monitor.buffer_for(channel.channel_id))
                table.add_row(
                    marker,
                    f"{channel.freq_mhz:.3f}",
                    channel.name,
                    channel.description,
                    str(count),
                    style=row_style,
                )

        title = (
            f"[bold]ACARS Channels[/bold] - "
            f"page {self.monitor.page_index + 1}/{self.monitor.page_count} "
            f"({self.monitor.page_range_label()})"
        )
        return Panel(
            table,
            title=title,
            border_style="cyan",
            padding=(0, 0),
            style="none",
        )

    def _message_panel(self, channel: AcarsChannel) -> Panel:
        lines: List[AcarsLine] = list(self.monitor.buffer_for(channel.channel_id))
        if not lines:
            body = _dim_text(
                f"Listening on {channel.freq_mhz:.3f} MHz - {channel.name}. "
                "ACARS messages appear here."
            )
        else:
            parts: List[RenderableType] = []
            for line in reversed(lines):
                msg = line.message
                row = Text()
                row.append(line.timestamp, style="dim")
                row.append("  ")
                row.append(msg.tail or "-", style="bold")
                row.append("  ")
                row.append(msg.label, style="yellow")
                if msg.flight:
                    row.append("  ")
                    row.append(msg.flight, style="cyan")
                if msg.msgno:
                    row.append("  ")
                    row.append(f"#{msg.msgno}", style="dim")
                row.append("  ")
                summary = msg.text or "(empty)"
                if len(summary) > 72:
                    summary = summary[:69] + "..."
                row.append(summary)
                parts.append(row)
            body = Text("\n").join(parts)

        title = (
            f"[bold]Live ACARS[/bold] - {channel.name} "
            f"({channel.freq_mhz:.3f} MHz) - last {MAX_ACARS_MESSAGES}"
        )
        return Panel(
            body,
            title=title,
            border_style="green",
            padding=(0, 1),
            style="none",
        )

    def _footer(self) -> RenderableType:
        text = Text()
        text.append("↑", style="bold cyan")
        text.append(" ")
        text.append("↓", style="bold cyan")
        text.append(" channel", style="dim")
        text.append("  ·  ")
        text.append("g", style="bold cyan")
        text.append(" ")
        text.append("G", style="bold cyan")
        text.append(" pages", style="dim")
        text.append("  ·  ")
        text.append("D", style="bold cyan")
        text.append(" ADS-B", style="dim")
        text.append("  ·  ")
        text.append("R", style="bold cyan")
        text.append(" radio", style="dim")
        text.append("  ·  ")
        text.append_text(_dim_text("Ctrl+C stop"))
        return Align.center(text)

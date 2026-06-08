"""VHF radio monitor dashboard with channel list and live transcripts."""

from __future__ import annotations

from typing import List

from rich import box
from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from aircraftx import __app_name__
from aircraftx.config import MAX_RADIO_TRANSCRIPTS, WAVEFORM_HEIGHT, RadioConfig
from aircraftx.dsp.waveform import WaveformView
from aircraftx.radio.channels import AirbandChannel
from aircraftx.radio.voice_monitor import TranscriptLine, VoiceMonitor
from aircraftx.ui.bars import FullWidthBar
from aircraftx.ui.display import _dim_text


class RadioDisplay:
    def __init__(self, monitor: VoiceMonitor, radio: RadioConfig) -> None:
        self.console = Console()
        self.monitor = monitor
        self.radio = radio

    def render(self) -> Group:
        channel = self.monitor.selected_channel()
        return Group(
            FullWidthBar(f" {__app_name__} — VHF Radio Monitor "),
            self._status_line(channel),
            self._channel_panel(),
            self._waveform_panel(),
            self._transcript_panel(channel),
            self._footer(),
        )

    def _status_line(self, channel: AirbandChannel) -> Text:
        text = Text()
        text.append(f"{channel.freq_mhz:.3f} MHz", style="bold cyan")
        text.append("  │  ")
        text.append(channel.name, style="bold yellow")
        text.append("  │  ")
        source = "local" if self.monitor.channel_source == "local" else "basic"
        text.append(source, style="bold white")
        text.append("  │  ")
        text.append(f"vol {self.monitor.volume:.1f}x", style="bold magenta")
        text.append("  │  ")
        level = self.monitor.squelch.last_rms
        squelch_style = "green" if self.monitor.gate_open else "dim"
        text.append(
            f"squelch {self.monitor.squelch.snr_db:.0f} dB", style=squelch_style
        )
        text.append("  │  ")
        text.append(f"lvl {level:.2f}", style="cyan" if level > 0.05 else "dim")
        text.append("  │  ")
        if self.monitor.audio_available:
            text.append("audio on", style="green")
        else:
            text.append("audio off", style="yellow")
        text.append("  │  ")
        stt = self.monitor.transcriber_status
        if self.monitor.stt_available:
            text.append(stt, style="green")
        elif stt == "loading":
            text.append("loading", style="dim")
        else:
            text.append("missing dependencies", style="yellow")
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
        table.add_column("Service", width=24)
        table.add_column("Description", ratio=1)
        table.add_column("Msgs", width=5, justify="right")

        page_start = self.monitor.page_index * self.monitor.channel_page_size
        page_rows = self.monitor.page_channels()
        if not page_rows:
            table.add_row("", "—", "—", _dim_text("No channels in this list"), "0")
        else:
            for offset, channel in enumerate(page_rows):
                idx = page_start + offset
                marker = "▶" if idx == self.monitor.selected_index else ""
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

        source = "Local" if self.monitor.channel_source == "local" else "Basic"
        source_style = (
            "bold green" if self.monitor.channel_source == "local" else "bold yellow"
        )
        title = (
            f"[bold]Airband Channels[/bold] — [{source_style}]{source}[/] · "
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

    def _waveform_panel(self) -> Panel:
        gate = "open" if self.monitor.gate_open else "closed"
        title = f"[bold]Signal[/bold] — squelch {gate}"
        body = WaveformView(
            self.monitor.waveform,
            gate_open=self.monitor.gate_open,
            height=WAVEFORM_HEIGHT,
        )
        return Panel(
            body,
            title=title,
            border_style="magenta",
            padding=(0, 0),
            expand=True,
            style="none",
        )

    def _transcript_panel(self, channel: AirbandChannel) -> Panel:
        lines: List[TranscriptLine] = list(self.monitor.buffer_for(channel.channel_id))
        if not lines:
            body = _dim_text(
                f"Listening on {channel.freq_mhz:.3f} MHz — {channel.name}. "
                "Transmissions appear here."
            )
        else:
            parts: List[RenderableType] = []
            for line in reversed(lines):
                row = Text()
                row.append(line.timestamp, style="dim")
                row.append("  ")
                row.append(line.text)
                parts.append(row)
            body = Text("\n").join(parts)

        title = (
            f"[bold]Live Transcript[/bold] — {channel.name} "
            f"({channel.freq_mhz:.3f} MHz) · last {MAX_RADIO_TRANSCRIPTS}"
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
        text.append("L", style="bold cyan")
        text.append(" local", style="dim")
        text.append("  ·  ")
        text.append("B", style="bold cyan")
        text.append(" basic", style="dim")
        text.append("  ·  ")
        text.append("g", style="bold cyan")
        text.append(" ")
        text.append("G", style="bold cyan")
        text.append(" pages", style="dim")
        text.append("  ·  ")
        text.append("[", style="bold cyan")
        text.append(" ")
        text.append("]", style="bold cyan")
        text.append(" squelch", style="dim")
        text.append("  ·  ")
        text.append("-", style="bold cyan")
        text.append(" ")
        text.append("+", style="bold cyan")
        text.append(" volume", style="dim")
        text.append("  ·  ")
        text.append("D", style="bold cyan")
        text.append(" ADS-B", style="dim")
        text.append("  ·  ")
        text.append("C", style="bold cyan")
        text.append(" ACARS", style="dim")
        text.append("  ·  ")
        text.append_text(_dim_text("Ctrl+C stop"))
        return Align.center(text)

"""Shared full-width terminal bar renderables."""

from __future__ import annotations

from typing import Iterator

from rich.console import Console
from rich.segment import Segment
from rich.text import Text


class FullWidthBar:
    """Single row styled edge-to-edge; resets terminal SGR after the line."""

    def __init__(self, content: str, style: str = "bold white on blue") -> None:
        self._content = content
        self._style = style

    def __rich_console__(
        self, console: Console, options
    ) -> Iterator[Segment]:  # noqa: ANN001
        line = Text(self._content, style=self._style, justify="center")
        for row in console.render_lines(line, options, pad=True):
            yield from row
            yield Segment("\x1b[0m")
            yield Segment.line()

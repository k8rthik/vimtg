"""TooSmallScreen — shown instead of a garbled layout on tiny terminals.

VimTGApp pushes it while the terminal is below MIN_WIDTH x MIN_HEIGHT
and pops it as soon as there is room again. It swallows every key
(Ctrl-Q still quits), so nothing is edited blind.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Static

from vimtg.tui.theme import COLORS

MIN_WIDTH = 30
MIN_HEIGHT = 8


def fits(width: int, height: int) -> bool:
    """True when the terminal is big enough (0 = size not known yet)."""
    if not width or not height:
        return True
    return width >= MIN_WIDTH and height >= MIN_HEIGHT


def notice(width: int, height: int) -> Text:
    t = Text(justify="center")
    t.append("Terminal too small\n", style=f"bold {COLORS['warning']}")
    t.append(f"{width}x{height}, need {MIN_WIDTH}x{MIN_HEIGHT}\n")
    t.append("Resize, or Ctrl-Q to quit", style="dim")
    return t


class TooSmallScreen(Screen[None]):
    """A centered notice; nothing else is drawn or editable."""

    DEFAULT_CSS = f"""
    TooSmallScreen {{
        align: center middle;
        background: {COLORS['bg']};
    }}
    #too-small {{ width: 100%; height: auto; }}
    """

    def __init__(self, width: int, height: int) -> None:
        super().__init__()
        self._width = width
        self._height = height
        self._pushed = False

    def compose(self) -> ComposeResult:
        yield Static(notice(self._width, self._height), id="too-small")

    def show_size(self, width: int, height: int) -> None:
        self._width, self._height = width, height
        self.query_one("#too-small", Static).update(notice(width, height))

    def on_screen_resume(self) -> None:
        """Back on top after a screen above it closed: the terminal may
        have grown meanwhile. (The first resume is the push itself, made
        from a resize event that app.size has not caught up with yet.)"""
        if self._pushed and fits(*self.app.size):
            self.app.pop_screen()
        self._pushed = True

    def on_key(self, event: Key) -> None:
        event.prevent_default()
        event.stop()

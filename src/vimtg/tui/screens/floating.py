"""FloatingScreen — the one shape every auxiliary view takes.

A lazy.nvim-style floating window: a bordered box centred over whatever
screen is below, which stays visible, dimmed, behind it. The border
title names the view and the bottom border lists its close keys, so
History, Help, `:messages`, the settings, the merge resolver, and the
sample hand all open and close the same way. A floating view opened
from another (`?` inside History) floats above both.

Subclasses yield their content from `compose_window`; it lands inside
the window container (`#<WINDOW_ID>`), laid out vertically.
"""

from __future__ import annotations

from typing import ClassVar, TypeVar

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen

from vimtg.tui.theme import COLORS

ResultT = TypeVar("ResultT")

CLOSE_HINT = "q / Esc close"


class FloatingScreen(ModalScreen[ResultT]):
    """A modal floating window over the screen below."""

    DEFAULT_CSS = f"""
    FloatingScreen {{
        align: center middle;
        background: rgba(0, 0, 0, 0.55);
    }}
    FloatingScreen > .floating-window {{
        width: 90%;
        height: 85%;
        max-width: 140;
        layout: vertical;
        background: {COLORS['bg']};
        border: round {COLORS['tag']};
        border-title-color: {COLORS['tag']};
        border-title-style: bold;
        border-subtitle-color: {COLORS['comment']};
    }}
    """

    WINDOW_ID: ClassVar[str] = "floating-window"

    def __init__(self, title: str, close_hint: str = CLOSE_HINT) -> None:
        super().__init__()
        self._window_title = title
        self._close_hint = close_hint

    def compose(self) -> ComposeResult:
        window = Container(id=self.WINDOW_ID, classes="floating-window")
        window.border_title = f" {self._window_title} "
        window.border_subtitle = f" {self._close_hint} "
        with window:
            yield from self.compose_window()

    def compose_window(self) -> ComposeResult:
        """The window's content, top to bottom."""
        yield from ()

    @property
    def window(self) -> Container:
        return self.query_one(f"#{self.WINDOW_ID}", Container)

    def set_window_title(self, title: str) -> None:
        self._window_title = title
        if self.is_mounted:
            self.window.border_title = f" {title} "

"""HelpScreen — full-screen help overlay.

Opened by `:help` (overview) or `:help <command>` (single topic) and F1.
Navigable with j/k, Ctrl-D/U, gg/G, Home/End; dismissed with q, Esc, or ?.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Static

from vimtg.editor.help_text import get_help
from vimtg.tui.key_translator import translate
from vimtg.tui.keys import (
    CLOSE_KEYS,
    HELP_KEY,
    NAV_HINTS,
    PENDING,
    VimNav,
    render_hints,
)
from vimtg.tui.theme import COLORS

HINTS = (*NAV_HINTS, ("q/Esc/?", "close"))

_HEADER = "═══ vimtg Help ═══════════════════════════════════════"


class HelpScreen(Screen[None]):
    """Full-screen help overlay, navigable with j/k, dismissible with q."""

    CSS = f"""
    #help-scroll {{
        height: 1fr;
        scrollbar-size: 1 1;
    }}
    #help-body {{
        padding: 0 2;
    }}
    #help-footer {{
        height: 1;
        dock: bottom;
        background: {COLORS['bg']};
    }}
    """

    def __init__(self, topic: str | None = None) -> None:
        super().__init__()
        self._topic = topic
        self._nav = VimNav()

    def compose(self) -> ComposeResult:
        yield VerticalScroll(Static(id="help-body"), id="help-scroll")
        yield Static(id="help-footer")

    def on_mount(self) -> None:
        body = self.query_one("#help-body", Static)
        text = Text()
        text.append(f"\n{_HEADER}\n\n", style=f"bold {COLORS['mode_command']}")
        text.append(get_help(self._topic))
        text.append("\n")
        body.update(text)

        self.query_one("#help-footer", Static).update(render_hints(HINTS))

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+c":
            return
        event.prevent_default()
        event.stop()

        key = translate(event.key)
        scroll = self.query_one("#help-scroll", VerticalScroll)

        if key in CLOSE_KEYS or key == HELP_KEY:
            self.app.pop_screen()
            return
        step = self._nav.feed(key, scroll.size.height)
        if step == PENDING:
            return
        if step == "home":
            scroll.scroll_home(animate=False)
        elif step == "end":
            scroll.scroll_end(animate=False)
        elif isinstance(step, int):
            scroll.scroll_relative(y=step, animate=False)

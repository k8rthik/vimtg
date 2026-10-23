"""HelpScreen — the floating help window.

Opened by `:help` (overview) or `:help <command>` (single topic), F1,
and `?` on every auxiliary screen; `:messages` shows its text in the
same window. Navigable with j/k, Ctrl-D/U, gg/G, Home/End; dismissed
with q, Esc, or ?.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.events import Key
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
from vimtg.tui.screens.floating import FloatingScreen
from vimtg.tui.theme import COLORS

HINTS = (*NAV_HINTS, ("q/Esc/?", "close"))

HELP_TITLE = "vimtg Help"


class HelpScreen(FloatingScreen[None]):
    """Floating help window, navigable with j/k, dismissible with q."""

    WINDOW_ID = "help-window"
    CSS = f"""
    #help-scroll {{
        height: 1fr;
        scrollbar-size: 1 1;
    }}
    #help-body {{
        padding: 0 1;
    }}
    #help-footer {{
        height: 1;
        background: {COLORS['bg']};
    }}
    """

    def __init__(
        self,
        topic: str | None = None,
        *,
        body: str | None = None,
        title: str = HELP_TITLE,
    ) -> None:
        """`body` replaces the help text (e.g. :messages), under `title`."""
        super().__init__(title if body is not None or topic is None else f"{title}: {topic}")
        self._topic = topic
        self._body = body
        self._nav = VimNav()

    def compose_window(self) -> ComposeResult:
        yield VerticalScroll(Static(id="help-body"), id="help-scroll")
        yield Static(id="help-footer")

    def on_mount(self) -> None:
        self._show_body()
        self.query_one("#help-footer", Static).update(render_hints(HINTS))

    def _show_body(self) -> None:
        text = Text()
        text.append(self._body if self._body is not None else get_help(self._topic))
        text.append("\n")
        self.query_one("#help-body", Static).update(text)

    def on_key(self, event: Key) -> None:
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

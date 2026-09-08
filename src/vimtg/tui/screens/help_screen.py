"""HelpScreen — full-screen help overlay.

Opened by `:help` (overview) or `:help <command>` (single topic) and F1.
Navigable with j/k, Ctrl-D/U, g/G; dismissed with q or Escape.
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
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scrolling import scroll_step_for_key

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

        footer = self.query_one("#help-footer", Static)
        hint = Text()
        hint.append(" j/k", style=f"bold {COLORS['quantity']}")
        hint.append(" scroll  ", style="dim")
        hint.append("Ctrl-D/U", style=f"bold {COLORS['quantity']}")
        hint.append(" half page  ", style="dim")
        hint.append("g/G", style=f"bold {COLORS['quantity']}")
        hint.append(" top/bottom  ", style="dim")
        hint.append("q", style=f"bold {COLORS['quantity']}")
        hint.append(" close", style="dim")
        footer.update(hint)

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+c":
            return
        event.prevent_default()
        event.stop()

        key = translate(event.key)
        scroll = self.query_one("#help-scroll", VerticalScroll)

        if key in ("q", "escape"):
            self.app.pop_screen()
            return
        step = scroll_step_for_key(key, scroll.size.height)
        if step == "home":
            scroll.scroll_home(animate=False)
        elif step == "end":
            scroll.scroll_end(animate=False)
        elif isinstance(step, int):
            scroll.scroll_relative(y=step, animate=False)

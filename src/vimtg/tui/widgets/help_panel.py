"""Help panel — the g? cheat sheet docked under the deck.

A short reference built from the key spec's quick hints (the rows the
which-key popup shows with nothing pending), one line per group; F1
opens the full help. It scrolls with j/k, Ctrl-D/U, gg/G and Home/End
when the terminal is too short for it.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from vimtg.editor.keyspec import quick_hints
from vimtg.tui.keys import PENDING, VimNav
from vimtg.tui.theme import COLORS


def render_cheat_sheet() -> Text:
    """The panel's content: a title line, then each quick-hint group."""
    t = Text()
    t.append(" Cheat sheet ", style=f"bold {COLORS['mana_blue']}")
    t.append("  F1 full help · ? or Esc close\n", style="dim")
    for section, rows in quick_hints().items():
        t.append(f" {section}: ", style=f"bold {COLORS['fg']}")
        for i, (key, desc) in enumerate(rows):
            t.append(key, style=f"bold {COLORS['quantity']}")
            t.append(f" {desc}", style="dim")
            if i < len(rows) - 1:
                t.append("  ")
        t.append("\n")
    return t


class HelpPanel(VerticalScroll):
    """The g? cheat sheet, scrollable."""

    can_focus = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._nav = VimNav()

    def compose(self) -> ComposeResult:
        yield Static(render_cheat_sheet(), id="help-panel-body")

    def scroll_by_key(self, key: str) -> bool:
        """Apply a vim scroll key; False when `key` is not a scroll key."""
        step = self._nav.feed(key, self.size.height)
        if step is None:
            return False
        if step == PENDING:
            return True
        if step == "home":
            self.scroll_home(animate=False)
        elif step == "end":
            self.scroll_end(animate=False)
        elif isinstance(step, int):
            self.scroll_relative(y=step, animate=False)
        return True

    def open(self) -> None:
        """Show the panel from the top — a reopen never resumes mid-list."""
        self.display = True
        self._nav.reset()
        self.scroll_home(animate=False)

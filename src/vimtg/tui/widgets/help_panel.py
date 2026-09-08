"""Help panel — toggleable inline overlay showing the keybinding reference.

A scrolling container: the panel is docked at the bottom with a capped
height, and the overview runs to well over a hundred lines, so j/k,
Ctrl-D/U, and g/G page through it exactly as in the full help screen.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from vimtg.editor.help_text import HELP_OVERVIEW, is_section_header
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scrolling import scroll_step_for_key


def render_help_overview() -> Text:
    """The panel's full content: title, hint line, and HELP_OVERVIEW."""
    t = Text()
    t.append(" Help ", style=f"bold {COLORS['mana_blue']}")
    t.append(
        "  ? or Escape close · j/k scroll · Ctrl-D/U half page · g/G top/bottom\n",
        style="dim",
    )
    t.append(f" {'─' * 50}\n", style=f"dim {COLORS['comment']}")
    for line in HELP_OVERVIEW.split("\n"):
        if is_section_header(line):
            t.append(f" {line}\n", style=f"bold {COLORS['fg']}")
        else:
            t.append(f" {line}\n", style="dim")
    return t


class HelpPanel(VerticalScroll):
    """Full help overlay rendered from HELP_OVERVIEW, scrollable."""

    can_focus = False

    def compose(self) -> ComposeResult:
        yield Static(render_help_overview(), id="help-panel-body")

    def scroll_by_key(self, key: str) -> bool:
        """Apply a vim scroll key; False when `key` is not a scroll key."""
        step = scroll_step_for_key(key, self.size.height)
        if step is None:
            return False
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
        self.scroll_home(animate=False)

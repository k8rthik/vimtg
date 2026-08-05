"""Help panel — toggleable overlay showing keybinding reference."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from vimtg.editor.help_text import HELP_OVERVIEW, is_section_header
from vimtg.tui.theme import COLORS


class HelpPanel(Static):
    """Full help overlay rendered from HELP_OVERVIEW."""

    def render(self) -> Text:
        t = Text()
        t.append(" Help ", style=f"bold {COLORS['mana_blue']}")
        t.append("  Press ? or Escape to close\n", style="dim")
        t.append(f" {'─' * 50}\n", style=f"dim {COLORS['comment']}")
        for line in HELP_OVERVIEW.split("\n"):
            if is_section_header(line):
                t.append(f" {line}\n", style=f"bold {COLORS['fg']}")
            else:
                t.append(f" {line}\n", style="dim")
        return t

"""StatusLine widget — shows mode, filename, card count, and cursor position."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.editor.modes import Mode
from vimtg.tui.theme import COLORS

MODE_DISPLAY: dict[Mode, tuple[str, str]] = {
    Mode.NORMAL: ("-- NORMAL --", COLORS["mode_normal"]),
    Mode.INSERT: ("-- INSERT --", COLORS["mode_insert"]),
    Mode.VISUAL: ("-- VISUAL --", COLORS["mode_visual"]),
    Mode.VISUAL_LINE: ("-- V-LINE --", COLORS["mode_visual"]),
    Mode.COMMAND: ("", COLORS["mode_command"]),
    Mode.SEARCH: ("", COLORS["mode_command"]),
}


class StatusLine(Static):
    """Bottom status bar showing editor state."""

    mode: reactive[Mode] = reactive(Mode.NORMAL)
    filename: reactive[str] = reactive("")
    modified: reactive[bool] = reactive(False)
    card_count: reactive[int] = reactive(0)
    cursor_line: reactive[int] = reactive(0)
    total_lines: reactive[int] = reactive(0)

    def render(self) -> Text:
        t = Text()
        mode_text, mode_color = MODE_DISPLAY.get(self.mode, ("", "white"))
        t.append(f" {mode_text} ", style=f"bold {mode_color}")
        t.append(f" {self.filename}", style="bold")
        if self.modified:
            t.append(" [+]", style=f"bold {COLORS['mana_red']}")
        t.append(f"  {self.card_count} cards", style="dim")
        t.append(f"  Ln {self.cursor_line + 1}/{self.total_lines}", style="dim")
        return t

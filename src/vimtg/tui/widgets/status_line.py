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
    vcs_snapshot_count: reactive[int] = reactive(0)
    recording_register: reactive[str] = reactive("")
    pending_keys: reactive[str] = reactive("")
    lint_error_count: reactive[int] = reactive(0)
    lint_warning_count: reactive[int] = reactive(0)
    cursor_lint: reactive[str] = reactive("")  # reason for the cursor row
    cursor_lint_level: reactive[str] = reactive("")  # "error" | "warning"
    plan_status: reactive[str] = reactive("")  # "vs Tron -4/+4" when a plan is active
    plan_unbalanced: reactive[bool] = reactive(False)
    # Card database state: "card data as of 2026-10-01", sync progress,
    # or the no-data badge; attention highlights it (no data / stale)
    card_data: reactive[str] = reactive("")
    card_data_attention: reactive[bool] = reactive(False)

    _CURSOR_LINT_MAX = 60

    def render(self) -> Text:
        t = Text()
        mode_text, mode_color = MODE_DISPLAY.get(self.mode, ("", "white"))
        t.append(f" {mode_text} ", style=f"bold {mode_color}")
        if self.recording_register:
            # Right after the mode, where it survives a narrow terminal:
            # a stray q starts recording, and this is how to get out
            t.append(
                f" recording @{self.recording_register} (q stops) ",
                style=f"bold {COLORS['bg']} on {COLORS['error']}",
            )
        t.append(f" {self.filename}", style="bold")
        if self.modified:
            t.append(" [+]", style=f"bold {COLORS['mana_red']}")
        t.append(f"  {self.card_count} cards", style="dim")
        if self.lint_error_count:
            t.append(f"  ✗{self.lint_error_count}", style=f"bold {COLORS['error']}")
        if self.lint_warning_count:
            t.append(
                f"  !{self.lint_warning_count}", style=f"bold {COLORS['warning']}"
            )
        if self.cursor_lint:
            reason = self.cursor_lint
            if len(reason) > self._CURSOR_LINT_MAX:
                reason = reason[: self._CURSOR_LINT_MAX - 1] + "…"
            sign = "✗" if self.cursor_lint_level == "error" else "!"
            color = COLORS["error"] if self.cursor_lint_level == "error" else COLORS["warning"]
            t.append(f"  {sign} {reason}", style=color)
        if self.plan_status:
            t.append(f"  {self.plan_status}", style=f"bold {COLORS['sideboard']}")
            if self.plan_unbalanced:
                t.append(" !", style=f"bold {COLORS['warning']}")
        if self.vcs_snapshot_count:
            t.append(f"  {self.vcs_snapshot_count} snapshots", style="dim")
        if self.pending_keys:
            t.append(f"  {self.pending_keys}", style=f"bold {COLORS['quantity']}")
        if self.card_data:
            style = f"bold {COLORS['warning']}" if self.card_data_attention else "dim"
            t.append(f"  {self.card_data}", style=style)
        t.append(f"  Ln {self.cursor_line + 1}/{self.total_lines}", style="dim")
        return t

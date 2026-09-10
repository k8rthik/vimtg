"""Branches panel — renders branch list with current branch highlighted."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.vcs import VCSBranch
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scroll_panel import HEADER_ROWS, fit_line, render_panel_header
from vimtg.tui.widgets.scrolling import (
    WHEEL_LINES,
    compute_scroll_offset,
    resolved_viewport,
    wheel_scroll,
)

DEFAULT_VIEWPORT = 12


class BranchesPanel(Static):
    """Renders branch list for the history screen."""

    default_viewport: int = DEFAULT_VIEWPORT

    branches: reactive[list[VCSBranch]] = reactive(list, recompose=False)
    current_branch: reactive[str] = reactive("main")
    selected: reactive[int] = reactive(0)
    focused_panel: reactive[bool] = reactive(False)
    scroll_pos: reactive[int] = reactive(0)

    @property
    def max_visible(self) -> int:
        return resolved_viewport(self.size.height, self.default_viewport, HEADER_ROWS)

    def render(self) -> Text:
        t = render_panel_header(
            "Branches", self.focused_panel, self.size.width,
            Text(f"  ({len(self.branches)})", style="dim"),
        )
        if not self.branches:
            t.append("  (no branches)\n", style="dim")
            return t

        start = self.scroll_pos
        end = min(start + self.max_visible, len(self.branches))
        for i in range(start, end):
            branch = self.branches[i]
            is_current = branch.name == self.current_branch
            is_selected = i == self.selected and self.focused_panel
            prefix = " * " if is_current else "   "
            style = ""
            if is_selected:
                style = f"bold on {COLORS['cursor_bg']}"
            elif is_current:
                style = f"bold {COLORS['mana_green']}"
            t.append_text(fit_line(Text(f"{prefix}{branch.name}", style=style), self.size.width))
            t.append("\n")
        return t

    # ── Selection ─────────────────────────────────────────

    def select_next(self) -> None:
        self.select_by(1)

    def select_prev(self) -> None:
        self.select_by(-1)

    def select_first(self) -> None:
        self.select_by(-len(self.branches))

    def select_last(self) -> None:
        self.select_by(len(self.branches))

    def select_by(self, delta: int) -> None:
        if self.branches:
            self.selected = max(0, min(self.selected + delta, len(self.branches) - 1))
        else:
            self.selected = 0
        self.scroll_pos = compute_scroll_offset(
            self.selected, self.scroll_pos, len(self.branches), self.max_visible,
            scrolloff=0,
        )

    def clamp_selection(self) -> None:
        self.select_by(0)

    def get_selected_branch(self) -> VCSBranch | None:
        if 0 <= self.selected < len(self.branches):
            return self.branches[self.selected]
        return None

    # ── Mouse wheel ───────────────────────────────────────

    def wheel(self, delta: int) -> None:
        self.scroll_pos, self.selected = wheel_scroll(
            self.scroll_pos, self.selected, delta, len(self.branches),
            self.max_visible, scrolloff=0,
        )

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        self.wheel(WHEEL_LINES)

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        self.wheel(-WHEEL_LINES)

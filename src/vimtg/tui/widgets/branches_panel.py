"""Branches panel — renders branch list with current branch highlighted."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.vcs import VCSBranch
from vimtg.tui.theme import COLORS


class BranchesPanel(Static):
    """Renders branch list for the history screen."""

    branches: reactive[list[VCSBranch]] = reactive(list, recompose=False)
    current_branch: reactive[str] = reactive("main")
    selected: reactive[int] = reactive(0)
    focused_panel: reactive[bool] = reactive(False)

    def render(self) -> Text:
        t = Text()
        border_color = COLORS["mana_green"] if self.focused_panel else COLORS["comment"]
        t.append(" Branches", style=f"bold {border_color}")
        t.append(f"  ({len(self.branches)})\n", style="dim")
        t.append(f" {'─' * 28}\n", style=f"dim {COLORS['comment']}")

        if not self.branches:
            t.append("  (no branches)\n", style="dim")
            return t

        for i, branch in enumerate(self.branches):
            is_current = branch.name == self.current_branch
            is_selected = i == self.selected and self.focused_panel
            prefix = " * " if is_current else "   "
            style = ""
            if is_selected:
                style = f"bold on {COLORS['cursor_bg']}"
            elif is_current:
                style = f"bold {COLORS['mana_green']}"
            t.append(f"{prefix}{branch.name}", style=style)
            t.append("\n")
        return t

    def select_next(self) -> None:
        if self.branches:
            self.selected = min(self.selected + 1, len(self.branches) - 1)

    def select_prev(self) -> None:
        self.selected = max(self.selected - 1, 0)

    def get_selected_branch(self) -> VCSBranch | None:
        if 0 <= self.selected < len(self.branches):
            return self.branches[self.selected]
        return None

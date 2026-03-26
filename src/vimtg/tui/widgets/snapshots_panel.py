"""Snapshots panel — renders snapshot log like git log."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.vcs import VCSSnapshot
from vimtg.tui.theme import COLORS


class SnapshotsPanel(Static):
    """Renders snapshot history for the history screen."""

    snapshots: reactive[list[VCSSnapshot]] = reactive(list, recompose=False)
    selected: reactive[int] = reactive(0)
    focused_panel: reactive[bool] = reactive(False)
    scroll_offset: reactive[int] = reactive(0)

    def render(self) -> Text:
        t = Text()
        border_color = COLORS["mana_blue"] if self.focused_panel else COLORS["comment"]
        t.append(" History", style=f"bold {border_color}")
        t.append(f"  ({len(self.snapshots)})\n", style="dim")
        t.append(f" {'─' * 28}\n", style=f"dim {COLORS['comment']}")

        if not self.snapshots:
            t.append("  (no snapshots)\n", style="dim")
            t.append("  Press c to commit\n", style=f"dim {COLORS['comment']}")
            return t

        # Visible window (simple scroll)
        max_visible = 20
        start = self.scroll_offset
        end = min(start + max_visible, len(self.snapshots))

        for i in range(start, end):
            snap = self.snapshots[i]
            is_selected = i == self.selected and self.focused_panel

            # Hash (first 7 chars)
            short_hash = snap.id[:7]
            # Timestamp
            ts = snap.timestamp.strftime("%b %d %H:%M")
            # Tag indicator
            tag_str = ""
            if snap.tag:
                tag_str = f" ({snap.tag})"

            if is_selected:
                t.append(f" > ", style=f"bold {COLORS['quantity']}")
                t.append(short_hash, style=f"bold {COLORS['mana_blue']} on {COLORS['cursor_bg']}")
            else:
                t.append("   ", style="")
                t.append(short_hash, style=f"{COLORS['mana_blue']}")

            t.append(f" {ts}", style="dim")
            if tag_str:
                t.append(tag_str, style=f"bold {COLORS['sideboard']}")
            t.append("\n")

            # Description on next line
            desc = snap.description[:35]
            indent = "     " if not is_selected else "     "
            if is_selected:
                t.append(f"{indent}{desc}\n", style=f"on {COLORS['cursor_bg']}")
            else:
                t.append(f"{indent}{desc}\n", style="dim")

        return t

    def select_next(self) -> None:
        if self.snapshots:
            self.selected = min(self.selected + 1, len(self.snapshots) - 1)
            self._adjust_scroll()

    def select_prev(self) -> None:
        self.selected = max(self.selected - 1, 0)
        self._adjust_scroll()

    def _adjust_scroll(self) -> None:
        max_visible = 20
        if self.selected < self.scroll_offset:
            self.scroll_offset = self.selected
        elif self.selected >= self.scroll_offset + max_visible:
            self.scroll_offset = self.selected - max_visible + 1

    def get_selected_snapshot(self) -> VCSSnapshot | None:
        if 0 <= self.selected < len(self.snapshots):
            return self.snapshots[self.selected]
        return None

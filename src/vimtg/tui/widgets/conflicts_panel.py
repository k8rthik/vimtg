"""Conflicts panel — renders merge conflicts with per-card resolutions."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.deck_merge import CardKey, MergeConflict
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scrolling import WHEEL_LINES

_UNSET = "·"


def _qty(value: int | None) -> str:
    return _UNSET if value is None else str(value)


class ConflictsPanel(Static):
    """Table of merge conflicts: base / ours / theirs / chosen per card."""

    conflicts: reactive[tuple[MergeConflict, ...]] = reactive(tuple)
    # Only resolved keys appear; None means "omit the card"
    resolutions: reactive[dict[CardKey, int | None]] = reactive(dict)
    selected: reactive[int] = reactive(0)

    def render(self) -> Text:
        t = Text()
        t.append(" Conflicts", style=f"bold {COLORS['focus']}")
        resolved = sum(1 for c in self.conflicts if c.key in self.resolutions)
        t.append(
            f"  ({resolved}/{len(self.conflicts)} resolved)\n", style="dim"
        )
        t.append(f" {'─' * 56}\n", style=f"dim {COLORS['comment']}")

        if not self.conflicts:
            t.append("  (no conflicts)\n", style="dim")
            return t

        header = f"   {'Card':<28} {'Base':>4} {'Ours':>4} {'Thrs':>4}  Chosen"
        t.append(header + "\n", style=f"dim {COLORS['comment']}")

        for i, conflict in enumerate(self.conflicts):
            is_selected = i == self.selected
            key = conflict.key
            name = conflict.card_name
            if conflict.section.value != "main":
                name = f"{name} ({conflict.section.value})"
            if len(name) > 28:
                name = name[:27] + "…"

            if key in self.resolutions:
                chosen = self.resolutions[key]
                chosen_str = "omit" if chosen is None else str(chosen)
                chosen_style = f"bold {COLORS['mana_green']}"
            else:
                chosen_str = "?"
                chosen_style = f"bold {COLORS['sideboard']}"

            marker = " > " if is_selected else "   "
            row_style = f"on {COLORS['cursor_bg']}" if is_selected else ""

            t.append(marker, style=f"bold {COLORS['quantity']}")
            t.append(f"{name:<28}", style=f"bold {row_style}" if row_style else "")
            t.append(
                f" {_qty(conflict.base_quantity):>4}",
                style=f"dim {row_style}" if row_style else "dim",
            )
            t.append(
                f" {_qty(conflict.ours_quantity):>4}",
                style=f"{COLORS['mana_blue']} {row_style}".strip(),
            )
            t.append(
                f" {_qty(conflict.theirs_quantity):>4}",
                style=f"{COLORS['sideboard']} {row_style}".strip(),
            )
            t.append("  ")
            t.append(chosen_str, style=f"{chosen_style} {row_style}".strip())
            t.append("\n")
        return t

    def select_next(self) -> None:
        self.select_by(1)

    def select_prev(self) -> None:
        self.select_by(-1)

    def select_by(self, delta: int) -> None:
        if self.conflicts:
            self.selected = max(0, min(self.selected + delta, len(self.conflicts) - 1))
        else:
            self.selected = 0

    def select_first(self) -> None:
        self.select_by(-len(self.conflicts))

    def select_last(self) -> None:
        self.select_by(len(self.conflicts))

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        self.select_by(WHEEL_LINES)

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        self.select_by(-WHEEL_LINES)

    def get_selected_conflict(self) -> MergeConflict | None:
        if 0 <= self.selected < len(self.conflicts):
            return self.conflicts[self.selected]
        return None

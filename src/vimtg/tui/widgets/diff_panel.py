"""Diff panel — renders MTG-aware card diff with color-coded changes."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.deck import DeckSection
from vimtg.domain.deck_diff import CardChange, ChangeType, DeckDiff
from vimtg.tui.theme import COLORS


def _format_change_line(change: CardChange) -> Text:
    """Format a single card change as a Rich Text line."""
    t = Text()
    if change.change_type == ChangeType.ADDED:
        qty = change.new_quantity or 0
        t.append(f" + {qty} {change.card_name}", style=f"{COLORS['mana_green']}")
    elif change.change_type == ChangeType.REMOVED:
        qty = change.old_quantity or 0
        t.append(f" - {qty} {change.card_name}", style=f"{COLORS['mana_red']}")
    elif change.change_type == ChangeType.QUANTITY_CHANGED:
        old_q = change.old_quantity or 0
        new_q = change.new_quantity or 0
        t.append(f" ~ {change.card_name}", style=f"{COLORS['sideboard']}")
        t.append(f"  {old_q} \u2192 {new_q}", style=f"bold {COLORS['sideboard']}")
    elif change.change_type == ChangeType.SECTION_MOVED:
        old_sec = (change.old_section or DeckSection.MAIN).value
        new_sec = (change.new_section or DeckSection.MAIN).value
        t.append(f" \u21c4 {change.card_name}", style=f"{COLORS['mana_blue']}")
        t.append(f"  {old_sec} \u2192 {new_sec}", style=f"dim {COLORS['mana_blue']}")
    else:
        qty = change.new_quantity or change.old_quantity or 0
        t.append(f"   {qty} {change.card_name}", style="dim")
    return t


class DiffPanel(Static):
    """Renders MTG-aware card diff with color-coded changes."""

    diff: reactive[DeckDiff | None] = reactive(None, recompose=False)
    focused_panel: reactive[bool] = reactive(False)
    show_unchanged: reactive[bool] = reactive(False)

    def render(self) -> Text:
        t = Text()
        border_color = COLORS["quantity"] if self.focused_panel else COLORS["comment"]
        t.append(" Diff", style=f"bold {border_color}")
        t.append("\n")
        t.append(f" {'─' * 40}\n", style=f"dim {COLORS['comment']}")

        if self.diff is None:
            t.append("  Select a snapshot to view diff\n", style="dim")
            return t

        if not self.diff.has_changes:
            t.append("  (no changes)\n", style="dim")
            return t

        # Mainboard changes
        main_changes = [
            c for c in self.diff.changes
            if c.section == DeckSection.MAIN
            or c.old_section == DeckSection.MAIN
            or c.new_section == DeckSection.MAIN
        ]
        active_main = [
            c for c in main_changes
            if c.change_type != ChangeType.UNCHANGED
        ]
        if active_main or (self.show_unchanged and main_changes):
            t.append(" Mainboard:\n", style=f"bold {COLORS['fg']}")
            for change in main_changes:
                if change.change_type == ChangeType.UNCHANGED and not self.show_unchanged:
                    continue
                t.append_text(_format_change_line(change))
                t.append("\n")
            t.append("\n")

        # Sideboard changes
        side_changes = [
            c for c in self.diff.changes
            if c.section == DeckSection.SIDEBOARD
            or c.old_section == DeckSection.SIDEBOARD
            or c.new_section == DeckSection.SIDEBOARD
        ]
        active_side = [
            c for c in side_changes
            if c.change_type != ChangeType.UNCHANGED
        ]
        if active_side or (self.show_unchanged and side_changes):
            t.append(" Sideboard:\n", style=f"bold {COLORS['fg']}")
            for change in side_changes:
                if change.change_type == ChangeType.UNCHANGED and not self.show_unchanged:
                    continue
                t.append_text(_format_change_line(change))
                t.append("\n")
            t.append("\n")

        # Commander changes
        cmd_changes = [
            c for c in self.diff.changes
            if c.section == DeckSection.COMMANDER
            or c.old_section == DeckSection.COMMANDER
            or c.new_section == DeckSection.COMMANDER
        ]
        active_cmd = [
            c for c in cmd_changes
            if c.change_type != ChangeType.UNCHANGED
        ]
        if active_cmd or (self.show_unchanged and cmd_changes):
            t.append(" Commander:\n", style=f"bold {COLORS['fg']}")
            for change in cmd_changes:
                if change.change_type == ChangeType.UNCHANGED and not self.show_unchanged:
                    continue
                t.append_text(_format_change_line(change))
                t.append("\n")

        # Summary
        added = self.diff.added_count
        removed = self.diff.removed_count
        if added or removed:
            t.append(f" {'+' if added else ''}{added} added", style=f"dim {COLORS['mana_green']}")
            t.append("  ", style="dim")
            t.append(f"{'-' if removed else ''}{removed} removed", style=f"dim {COLORS['mana_red']}")
            t.append("\n")

        return t

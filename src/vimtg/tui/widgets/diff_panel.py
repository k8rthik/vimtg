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

        sections = (
            ("Mainboard", DeckSection.MAIN),
            ("Sideboard", DeckSection.SIDEBOARD),
            ("Commander", DeckSection.COMMANDER),
        )
        for label, section in sections:
            t.append_text(self._render_section(label, section))

        # Summary
        added = self.diff.added_count
        removed = self.diff.removed_count
        if added or removed:
            t.append(f" {'+' if added else ''}{added} added", style=f"dim {COLORS['mana_green']}")
            t.append("  ", style="dim")
            t.append(
                f"{'-' if removed else ''}{removed} removed",
                style=f"dim {COLORS['mana_red']}",
            )
            t.append("\n")

        return t

    def _render_section(self, label: str, section: DeckSection) -> Text:
        """Render one section's changes (empty Text when nothing to show)."""
        assert self.diff is not None
        changes = [
            c for c in self.diff.changes
            if section in (c.section, c.old_section, c.new_section)
        ]
        visible = [
            c for c in changes
            if self.show_unchanged or c.change_type != ChangeType.UNCHANGED
        ]
        has_active = any(c.change_type != ChangeType.UNCHANGED for c in changes)
        if not (has_active or (self.show_unchanged and changes)):
            return Text()

        t = Text()
        t.append(f" {label}:\n", style=f"bold {COLORS['fg']}")
        for change in visible:
            t.append_text(_format_change_line(change))
            t.append("\n")
        t.append("\n")
        return t

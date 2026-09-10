"""Diff panel — renders MTG-aware card diff with color-coded changes."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive

from vimtg.domain.deck import DeckSection
from vimtg.domain.deck_diff import CardChange, ChangeType, DeckDiff
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scroll_panel import ScrollablePanel

_SECTIONS = (
    ("Mainboard", DeckSection.MAIN),
    ("Sideboard", DeckSection.SIDEBOARD),
    ("Commander", DeckSection.COMMANDER),
)


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
        t.append(f"  {old_q} → {new_q}", style=f"bold {COLORS['sideboard']}")
    elif change.change_type == ChangeType.SECTION_MOVED:
        old_sec = (change.old_section or DeckSection.MAIN).value
        new_sec = (change.new_section or DeckSection.MAIN).value
        t.append(f" ⇄ {change.card_name}", style=f"{COLORS['mana_blue']}")
        t.append(f"  {old_sec} → {new_sec}", style=f"dim {COLORS['mana_blue']}")
    else:
        qty = change.new_quantity or change.old_quantity or 0
        t.append(f"   {qty} {change.card_name}", style="dim")
    return t


class DiffPanel(ScrollablePanel):
    """Renders MTG-aware card diff with color-coded changes."""

    title = "Diff"

    diff: reactive[DeckDiff | None] = reactive(None, recompose=False)
    show_unchanged: reactive[bool] = reactive(False)

    def watch_diff(self) -> None:
        self.scroll_to_top()

    def body_lines(self) -> list[Text]:
        if self.diff is None:
            return [Text("  Select a snapshot to view diff", style="dim")]
        if not self.diff.has_changes:
            return [Text("  (no changes)", style="dim")]

        lines: list[Text] = []
        for label, section in _SECTIONS:
            lines.extend(self._section_lines(label, section))

        added = self.diff.added_count
        removed = self.diff.removed_count
        if added or removed:
            summary = Text()
            summary.append(
                f" {'+' if added else ''}{added} added", style=f"dim {COLORS['mana_green']}"
            )
            summary.append("  ", style="dim")
            summary.append(
                f"{'-' if removed else ''}{removed} removed",
                style=f"dim {COLORS['mana_red']}",
            )
            lines.append(summary)
        return lines

    def _section_lines(self, label: str, section: DeckSection) -> list[Text]:
        """One section's changes (empty when nothing to show)."""
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
            return []
        lines = [Text(f" {label}:", style=f"bold {COLORS['fg']}")]
        lines.extend(_format_change_line(c) for c in visible)
        lines.append(Text(""))
        return lines

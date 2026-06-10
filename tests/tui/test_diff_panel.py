"""Tests for DiffPanel — section grouping, color-coded changes, summary."""

from __future__ import annotations

from vimtg.domain.deck import DeckSection
from vimtg.domain.deck_diff import CardChange, ChangeType, DeckDiff
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.diff_panel import DiffPanel, _format_change_line


def _added(name: str, qty: int, section: DeckSection = DeckSection.MAIN) -> CardChange:
    return CardChange(
        card_name=name,
        change_type=ChangeType.ADDED,
        section=section,
        new_quantity=qty,
        new_section=section,
    )


def _removed(name: str, qty: int, section: DeckSection = DeckSection.MAIN) -> CardChange:
    return CardChange(
        card_name=name,
        change_type=ChangeType.REMOVED,
        section=section,
        old_quantity=qty,
        old_section=section,
    )


def _qty_changed(
    name: str, old: int, new: int, section: DeckSection = DeckSection.MAIN
) -> CardChange:
    return CardChange(
        card_name=name,
        change_type=ChangeType.QUANTITY_CHANGED,
        section=section,
        old_quantity=old,
        new_quantity=new,
    )


def _moved(name: str, old: DeckSection, new: DeckSection, qty: int = 1) -> CardChange:
    return CardChange(
        card_name=name,
        change_type=ChangeType.SECTION_MOVED,
        section=new,
        old_quantity=qty,
        new_quantity=qty,
        old_section=old,
        new_section=new,
    )


def _unchanged(name: str, qty: int, section: DeckSection = DeckSection.MAIN) -> CardChange:
    return CardChange(
        card_name=name,
        change_type=ChangeType.UNCHANGED,
        section=section,
        old_quantity=qty,
        new_quantity=qty,
    )


def _styles_at(label: str, text) -> str:
    """Return concatenated style names spanning the position of `label`."""
    start = text.plain.index(label)
    styles: list[str] = []
    for span in text.spans:
        if span.start <= start < span.end:
            styles.append(str(span.style))
    return " ".join(styles)


# ── _format_change_line ────────────────────────────────────────────


class TestFormatChangeLine:
    def test_added_uses_plus_prefix(self) -> None:
        text = _format_change_line(_added("Lightning Bolt", 4))
        assert "+ 4 Lightning Bolt" in text.plain

    def test_added_uses_green(self) -> None:
        text = _format_change_line(_added("Lightning Bolt", 4))
        assert COLORS["mana_green"] in _styles_at("Lightning Bolt", text)

    def test_removed_uses_minus_prefix(self) -> None:
        text = _format_change_line(_removed("Lava Spike", 4))
        assert "- 4 Lava Spike" in text.plain

    def test_removed_uses_red(self) -> None:
        text = _format_change_line(_removed("Lava Spike", 4))
        assert COLORS["mana_red"] in _styles_at("Lava Spike", text)

    def test_quantity_changed_shows_arrow(self) -> None:
        text = _format_change_line(_qty_changed("Mountain", 4, 8))
        assert "Mountain" in text.plain
        assert "4 → 8" in text.plain

    def test_section_moved_shows_double_arrow(self) -> None:
        text = _format_change_line(
            _moved("Path to Exile", DeckSection.SIDEBOARD, DeckSection.MAIN, 2)
        )
        # Card line uses ⇄ (rightleftharpoons) and labels old → new
        assert "Path to Exile" in text.plain
        assert "⇄" in text.plain
        assert "→" in text.plain

    def test_unchanged_uses_dim_style(self) -> None:
        text = _format_change_line(_unchanged("Mountain", 4))
        assert "Mountain" in text.plain
        assert "dim" in _styles_at("Mountain", text)


# ── DiffPanel.render ───────────────────────────────────────────────


class TestDiffPanelEmpty:
    def test_no_diff_shows_placeholder(self) -> None:
        p = DiffPanel()
        text = p.render()
        assert "Select a snapshot" in text.plain

    def test_no_changes_renders_message(self) -> None:
        p = DiffPanel()
        p.diff = DeckDiff(changes=(_unchanged("Mountain", 4),))
        text = p.render()
        assert "(no changes)" in text.plain


class TestDiffPanelSections:
    def test_mainboard_section_only_shown_with_changes(self) -> None:
        p = DiffPanel()
        p.diff = DeckDiff(changes=(_added("Mountain", 4),))
        text = p.render()
        assert "Mainboard:" in text.plain
        assert "Sideboard:" not in text.plain
        assert "Commander:" not in text.plain

    def test_sideboard_section_shown_when_only_sideboard_changes(self) -> None:
        p = DiffPanel()
        p.diff = DeckDiff(
            changes=(_added("Negate", 2, DeckSection.SIDEBOARD),)
        )
        text = p.render()
        assert "Sideboard:" in text.plain
        assert "Mainboard:" not in text.plain

    def test_commander_section_shown_when_changes(self) -> None:
        p = DiffPanel()
        p.diff = DeckDiff(
            changes=(_added("Atraxa", 1, DeckSection.COMMANDER),)
        )
        text = p.render()
        assert "Commander:" in text.plain

    def test_section_moved_appears_in_both_old_and_new_section(self) -> None:
        """A move between sections is relevant to both old and new sections."""
        p = DiffPanel()
        p.diff = DeckDiff(
            changes=(_moved("Path to Exile", DeckSection.SIDEBOARD, DeckSection.MAIN, 2),)
        )
        text = p.render()
        assert "Mainboard:" in text.plain
        assert "Sideboard:" in text.plain


class TestDiffPanelShowUnchanged:
    def test_unchanged_hidden_by_default(self) -> None:
        p = DiffPanel()
        p.diff = DeckDiff(changes=(
            _added("Mountain", 4),
            _unchanged("Island", 4),
        ))
        text = p.render()
        assert "Mountain" in text.plain
        assert "Island" not in text.plain

    def test_unchanged_shown_when_enabled(self) -> None:
        p = DiffPanel()
        p.show_unchanged = True
        p.diff = DeckDiff(changes=(
            _added("Mountain", 4),
            _unchanged("Island", 4),
        ))
        text = p.render()
        assert "Mountain" in text.plain
        assert "Island" in text.plain

    def test_unchanged_commander_shown_with_show_unchanged(self) -> None:
        """Regression: Commander section used to ignore show_unchanged.

        When the mainboard has changes (so the diff renders past the
        has_changes guard) and the commander is unchanged, enabling
        show_unchanged should still surface the commander section.
        """
        p = DiffPanel()
        p.show_unchanged = True
        p.diff = DeckDiff(changes=(
            _added("Sol Ring", 1),
            _unchanged("Atraxa", 1, DeckSection.COMMANDER),
        ))
        text = p.render()
        assert "Commander:" in text.plain
        assert "Atraxa" in text.plain

    def test_unchanged_commander_hidden_when_show_unchanged_off(self) -> None:
        p = DiffPanel()
        p.show_unchanged = False
        p.diff = DeckDiff(changes=(
            _added("Sol Ring", 1),
            _unchanged("Atraxa", 1, DeckSection.COMMANDER),
        ))
        text = p.render()
        assert "Commander:" not in text.plain
        assert "Atraxa" not in text.plain


class TestDiffPanelSummary:
    def test_summary_shows_added_and_removed_counts(self) -> None:
        p = DiffPanel()
        p.diff = DeckDiff(changes=(
            _added("Mountain", 4),
            _added("Goblin Guide", 4),
            _removed("Lava Spike", 4),
        ))
        text = p.render()
        # added_count=2, removed_count=1
        assert "+2 added" in text.plain
        assert "-1 removed" in text.plain

    def test_no_summary_when_no_add_remove(self) -> None:
        p = DiffPanel()
        p.diff = DeckDiff(changes=(_qty_changed("Mountain", 4, 8),))
        text = p.render()
        assert "added" not in text.plain
        assert "removed" not in text.plain


class TestDiffPanelFocus:
    def test_focused_uses_active_border_color(self) -> None:
        p = DiffPanel()
        p.focused_panel = True
        text = p.render()
        assert COLORS["quantity"] in _styles_at("Diff", text)

    def test_unfocused_uses_dim_border_color(self) -> None:
        p = DiffPanel()
        p.focused_panel = False
        text = p.render()
        assert COLORS["comment"] in _styles_at("Diff", text)

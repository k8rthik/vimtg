"""Tests for the MTG-aware deck diff engine."""

from vimtg.domain.deck import DeckSection
from vimtg.domain.deck_diff import (
    CardChange,
    ChangeType,
    StatsDelta,
    compute_deck_diff,
)

# ── Fixtures ──────────────────────────────────────────────

OLD_DECK = """\
// Deck: Burn
// Format: modern

4 Goblin Guide
4 Monastery Swiftspear
2 Shock

SB: 2 Rest in Peace
"""

NEW_DECK = """\
// Deck: Burn
// Format: modern

4 Goblin Guide
4 Lightning Bolt
4 Monastery Swiftspear

SB: 2 Rest in Peace
SB: 1 Grafdigger's Cage
"""

EMPTY_DECK = ""


# ── compute_deck_diff ─────────────────────────────────────


class TestComputeDeckDiff:
    def test_added_card(self) -> None:
        diff = compute_deck_diff(OLD_DECK, NEW_DECK)
        added = [c for c in diff.changes if c.change_type == ChangeType.ADDED]
        names = {c.card_name for c in added}
        assert "Lightning Bolt" in names
        bolt = next(c for c in added if c.card_name == "Lightning Bolt")
        assert bolt.new_quantity == 4
        assert bolt.section == DeckSection.MAIN

    def test_removed_card(self) -> None:
        diff = compute_deck_diff(OLD_DECK, NEW_DECK)
        removed = [c for c in diff.changes if c.change_type == ChangeType.REMOVED]
        names = {c.card_name for c in removed}
        assert "Shock" in names
        shock = next(c for c in removed if c.card_name == "Shock")
        assert shock.old_quantity == 2
        assert shock.section == DeckSection.MAIN

    def test_unchanged_card(self) -> None:
        diff = compute_deck_diff(OLD_DECK, NEW_DECK)
        unchanged = [c for c in diff.changes if c.change_type == ChangeType.UNCHANGED]
        names = {c.card_name for c in unchanged}
        assert "Goblin Guide" in names
        assert "Monastery Swiftspear" in names

    def test_sideboard_added(self) -> None:
        diff = compute_deck_diff(OLD_DECK, NEW_DECK)
        added = [
            c for c in diff.changes
            if c.change_type == ChangeType.ADDED and c.section == DeckSection.SIDEBOARD
        ]
        assert any(c.card_name == "Grafdigger's Cage" for c in added)

    def test_sideboard_unchanged(self) -> None:
        diff = compute_deck_diff(OLD_DECK, NEW_DECK)
        sb_unchanged = [
            c for c in diff.changes
            if c.change_type == ChangeType.UNCHANGED and c.section == DeckSection.SIDEBOARD
        ]
        assert any(c.card_name == "Rest in Peace" for c in sb_unchanged)

    def test_quantity_changed(self) -> None:
        old = "4 Lightning Bolt\n3 Goblin Guide\n"
        new = "4 Lightning Bolt\n4 Goblin Guide\n"
        diff = compute_deck_diff(old, new)
        changed = [c for c in diff.changes if c.change_type == ChangeType.QUANTITY_CHANGED]
        assert len(changed) == 1
        assert changed[0].card_name == "Goblin Guide"
        assert changed[0].old_quantity == 3
        assert changed[0].new_quantity == 4

    def test_section_moved(self) -> None:
        old = "4 Lightning Bolt\n"
        new = "SB: 4 Lightning Bolt\n"
        diff = compute_deck_diff(old, new)
        moved = [c for c in diff.changes if c.change_type == ChangeType.SECTION_MOVED]
        assert len(moved) == 1
        assert moved[0].old_section == DeckSection.MAIN
        assert moved[0].new_section == DeckSection.SIDEBOARD

    def test_empty_to_deck(self) -> None:
        diff = compute_deck_diff(EMPTY_DECK, "4 Lightning Bolt\n")
        assert diff.added_count == 1
        assert diff.removed_count == 0

    def test_deck_to_empty(self) -> None:
        diff = compute_deck_diff("4 Lightning Bolt\n", EMPTY_DECK)
        assert diff.added_count == 0
        assert diff.removed_count == 1

    def test_identical_decks(self) -> None:
        diff = compute_deck_diff(OLD_DECK, OLD_DECK)
        assert not diff.has_changes
        assert all(c.change_type == ChangeType.UNCHANGED for c in diff.changes)

    def test_both_empty(self) -> None:
        diff = compute_deck_diff(EMPTY_DECK, EMPTY_DECK)
        assert len(diff.changes) == 0
        assert not diff.has_changes


class TestDeckDiffProperties:
    def test_mainboard_changes(self) -> None:
        diff = compute_deck_diff(OLD_DECK, NEW_DECK)
        main = diff.mainboard_changes
        # Should include Goblin Guide, Monastery Swiftspear, Lightning Bolt, Shock
        main_names = {c.card_name for c in main}
        assert "Goblin Guide" in main_names
        assert "Lightning Bolt" in main_names
        assert "Shock" in main_names

    def test_sideboard_changes(self) -> None:
        diff = compute_deck_diff(OLD_DECK, NEW_DECK)
        side = diff.sideboard_changes
        side_names = {c.card_name for c in side}
        assert "Rest in Peace" in side_names
        assert "Grafdigger's Cage" in side_names

    def test_has_changes_true(self) -> None:
        diff = compute_deck_diff(OLD_DECK, NEW_DECK)
        assert diff.has_changes

    def test_added_removed_counts(self) -> None:
        diff = compute_deck_diff(OLD_DECK, NEW_DECK)
        assert diff.added_count >= 1  # Lightning Bolt + Grafdigger's Cage
        assert diff.removed_count >= 1  # Shock


class TestCardChangeDataclass:
    def test_frozen(self) -> None:
        change = CardChange(
            card_name="Test",
            change_type=ChangeType.ADDED,
            section=DeckSection.MAIN,
            new_quantity=4,
        )
        try:
            change.card_name = "Mutated"  # type: ignore[misc]
            raise AssertionError("Expected FrozenInstanceError")
        except AttributeError:
            pass


class TestStatsDelta:
    def test_frozen(self) -> None:
        delta = StatsDelta(
            old_total=60,
            new_total=62,
            old_avg_cmc=1.8,
            new_avg_cmc=1.6,
            old_price=142.0,
            new_price=156.0,
            curve_delta={1: 2, 2: -2},
        )
        assert delta.new_total - delta.old_total == 2

    def test_none_prices(self) -> None:
        delta = StatsDelta(
            old_total=60,
            new_total=60,
            old_avg_cmc=2.0,
            new_avg_cmc=2.0,
            old_price=None,
            new_price=None,
            curve_delta={},
        )
        assert delta.old_price is None
        assert delta.new_price is None

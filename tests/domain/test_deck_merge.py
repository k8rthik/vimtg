"""Tests for the pure 3-way deck merge and change-replay logic."""

from __future__ import annotations

import pytest

from vimtg.domain.deck import DeckSection
from vimtg.domain.deck_diff import build_card_map, compute_deck_diff
from vimtg.domain.deck_merge import (
    CardKey,
    apply_card_changes,
    merged_map_to_deck_state,
    three_way_merge,
)

BOLT: CardKey = ("Lightning Bolt", DeckSection.MAIN)


def _state(*lines: str) -> str:
    return "\n".join(lines) + "\n"


class TestThreeWayDecisionTable:
    @pytest.mark.parametrize(
        ("base", "ours", "theirs", "expected"),
        [
            # Both sides agree (including both unchanged)
            ("4 Lightning Bolt", "4 Lightning Bolt", "4 Lightning Bolt", 4),
            ("2 Lightning Bolt", "3 Lightning Bolt", "3 Lightning Bolt", 3),
            # Only theirs changed
            ("4 Lightning Bolt", "4 Lightning Bolt", "2 Lightning Bolt", 2),
            # Only ours changed
            ("4 Lightning Bolt", "1 Lightning Bolt", "4 Lightning Bolt", 1),
        ],
    )
    def test_clean_quantity_outcomes(
        self, base: str, ours: str, theirs: str, expected: int
    ) -> None:
        result = three_way_merge(
            _state(base), _state(ours), _state(theirs)
        )
        assert not result.has_conflicts
        assert result.merged[BOLT] == expected

    def test_add_add_same_quantity_is_clean(self) -> None:
        result = three_way_merge(
            "", _state("4 Lightning Bolt"), _state("4 Lightning Bolt")
        )
        assert not result.has_conflicts
        assert result.merged[BOLT] == 4

    def test_one_side_deletes_unchanged_card(self) -> None:
        result = three_way_merge(
            _state("4 Lightning Bolt"), "", _state("4 Lightning Bolt")
        )
        assert not result.has_conflicts
        assert BOLT not in result.merged

    def test_modify_modify_conflicts(self) -> None:
        result = three_way_merge(
            _state("4 Lightning Bolt"),
            _state("3 Lightning Bolt"),
            _state("2 Lightning Bolt"),
        )
        assert result.has_conflicts
        (conflict,) = result.conflicts
        assert conflict.key == BOLT
        assert conflict.base_quantity == 4
        assert conflict.ours_quantity == 3
        assert conflict.theirs_quantity == 2
        assert BOLT not in result.merged

    def test_add_add_different_quantity_conflicts(self) -> None:
        result = three_way_merge(
            "", _state("4 Lightning Bolt"), _state("2 Lightning Bolt")
        )
        assert result.has_conflicts
        assert result.conflicts[0].base_quantity is None

    def test_delete_modify_conflicts(self) -> None:
        result = three_way_merge(
            _state("4 Lightning Bolt"),
            "",
            _state("2 Lightning Bolt"),
        )
        assert result.has_conflicts
        (conflict,) = result.conflicts
        assert conflict.ours_quantity is None
        assert conflict.theirs_quantity == 2

    def test_independent_cards_merge_cleanly(self) -> None:
        result = three_way_merge(
            _state("4 Lightning Bolt"),
            _state("4 Lightning Bolt", "4 Goblin Guide"),
            _state("4 Lightning Bolt", "2 Shock"),
        )
        assert not result.has_conflicts
        assert result.merged == {
            BOLT: 4,
            ("Goblin Guide", DeckSection.MAIN): 4,
            ("Shock", DeckSection.MAIN): 2,
        }

    def test_section_move_one_side_is_clean(self) -> None:
        """A move is a per-section remove+add; only one side moved it."""
        base = _state("4 Lightning Bolt")
        ours = _state("SB: 4 Lightning Bolt")  # we moved it to sideboard
        theirs = _state("4 Lightning Bolt")  # they left it alone
        result = three_way_merge(base, ours, theirs)
        assert not result.has_conflicts
        assert result.merged == {("Lightning Bolt", DeckSection.SIDEBOARD): 4}

    def test_move_vs_quantity_change_conflicts_in_old_section(self) -> None:
        base = _state("4 Lightning Bolt")
        ours = _state("SB: 4 Lightning Bolt")  # moved
        theirs = _state("2 Lightning Bolt")  # qty changed in place
        result = three_way_merge(base, ours, theirs)
        # Old-section key: ours deleted, theirs modified -> conflict.
        # New-section key: only ours added -> clean.
        assert len(result.conflicts) == 1
        assert result.conflicts[0].section == DeckSection.MAIN
        assert result.merged == {("Lightning Bolt", DeckSection.SIDEBOARD): 4}


class TestMergedMapToDeckState:
    def test_preserves_our_order_and_appends_theirs(self) -> None:
        ours = _state("4 Lightning Bolt", "4 Goblin Guide")
        merged = {
            ("Lightning Bolt", DeckSection.MAIN): 4,
            ("Goblin Guide", DeckSection.MAIN): 2,
            ("Shock", DeckSection.MAIN): 3,
        }
        state = merged_map_to_deck_state(merged, ours)
        parsed = build_card_map(state)
        assert parsed == {
            ("Lightning Bolt", DeckSection.MAIN): 4,
            ("Goblin Guide", DeckSection.MAIN): 2,
            ("Shock", DeckSection.MAIN): 3,
        }
        # Our cards keep their relative order; new cards come after
        bolt = state.index("Lightning Bolt")
        guide = state.index("Goblin Guide")
        shock = state.index("Shock")
        assert bolt < guide < shock

    def test_dropped_key_is_omitted(self) -> None:
        ours = _state("4 Lightning Bolt", "4 Goblin Guide")
        merged = {("Lightning Bolt", DeckSection.MAIN): 4}
        state = merged_map_to_deck_state(merged, ours)
        assert "Goblin Guide" not in state

    def test_sideboard_keys_serialize_to_sideboard(self) -> None:
        merged = {("Shock", DeckSection.SIDEBOARD): 2}
        state = merged_map_to_deck_state(merged, "")
        assert build_card_map(state) == {("Shock", DeckSection.SIDEBOARD): 2}


class TestApplyCardChanges:
    def test_replays_addition(self) -> None:
        diff = compute_deck_diff("", _state("2 Shock"))
        state = apply_card_changes(_state("4 Lightning Bolt"), diff.changes)
        assert build_card_map(state) == {
            BOLT: 4,
            ("Shock", DeckSection.MAIN): 2,
        }

    def test_replays_removal(self) -> None:
        diff = compute_deck_diff(_state("4 Lightning Bolt"), "")
        state = apply_card_changes(
            _state("4 Lightning Bolt", "4 Goblin Guide"), diff.changes
        )
        assert build_card_map(state) == {("Goblin Guide", DeckSection.MAIN): 4}

    def test_replays_quantity_change_over_existing(self) -> None:
        """Overlap policy: the replayed change wins."""
        diff = compute_deck_diff(
            _state("4 Lightning Bolt"), _state("2 Lightning Bolt")
        )
        state = apply_card_changes(_state("3 Lightning Bolt"), diff.changes)
        assert build_card_map(state) == {BOLT: 2}

    def test_add_skips_existing_key(self) -> None:
        diff = compute_deck_diff("", _state("2 Lightning Bolt"))
        state = apply_card_changes(_state("4 Lightning Bolt"), diff.changes)
        assert build_card_map(state) == {BOLT: 4}

    def test_replays_section_move(self) -> None:
        diff = compute_deck_diff(
            _state("4 Lightning Bolt"), _state("SB: 4 Lightning Bolt")
        )
        state = apply_card_changes(_state("4 Lightning Bolt"), diff.changes)
        assert build_card_map(state) == {
            ("Lightning Bolt", DeckSection.SIDEBOARD): 4
        }


class TestCommentHandling:
    def test_section_headers_dropped_not_mislocated(self) -> None:
        """Freeform comments (section headers) are dropped, never hoisted
        above unrelated cards where cleanup would mislabel sections."""
        ours = "// Creatures\n4 Goblin Guide\n\n// Spells\n4 Lightning Bolt\n"
        merged = {
            ("Goblin Guide", DeckSection.MAIN): 4,
            ("Lightning Bolt", DeckSection.MAIN): 4,
        }
        state = merged_map_to_deck_state(merged, ours)
        assert "// Creatures" not in state
        assert "// Spells" not in state
        assert build_card_map(state) == merged

    def test_apply_changes_drops_section_headers(self) -> None:
        ours = "// Creatures\n4 Goblin Guide\n"
        diff = compute_deck_diff("", _state("2 Shock"))
        state = apply_card_changes(ours, diff.changes)
        assert "// Creatures" not in state
        assert build_card_map(state) == {
            ("Goblin Guide", DeckSection.MAIN): 4,
            ("Shock", DeckSection.MAIN): 2,
        }

    def test_metadata_survives_merge(self) -> None:
        ours = "// Deck: Burn\n// Format: modern\n\n4 Goblin Guide\n"
        merged = {("Goblin Guide", DeckSection.MAIN): 4}
        state = merged_map_to_deck_state(merged, ours)
        assert "// Deck: Burn" in state
        assert "// Format: modern" in state


class TestPlanHandling:
    def test_plans_survive_merge_from_ours(self) -> None:
        ours = "4 Goblin Guide\nSB: 2 Shock\n\nVS: Tron\n    -1 Goblin Guide\n    +1 Shock\n"
        merged = {
            ("Goblin Guide", DeckSection.MAIN): 4,
            ("Shock", DeckSection.SIDEBOARD): 2,
        }
        state = merged_map_to_deck_state(merged, ours)
        assert "VS: Tron\n    -1 Goblin Guide\n    +1 Shock\n" in state

    def test_plans_survive_apply_changes(self) -> None:
        ours = "4 Goblin Guide\n\nVS: Tron\n    -1 Goblin Guide\n"
        diff = compute_deck_diff("", _state("2 Shock"))
        state = apply_card_changes(ours, diff.changes)
        assert "VS: Tron\n    -1 Goblin Guide\n" in state

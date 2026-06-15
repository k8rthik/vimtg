"""Tests for the deck diff service."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card
from vimtg.domain.deck_diff import ChangeType
from vimtg.services.deck_diff_service import DeckDiffService

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

OLD_STATE = "4 Lightning Bolt\n4 Goblin Guide\n"
NEW_STATE = "4 Lightning Bolt\n4 Monastery Swiftspear\n"


@pytest.fixture
def card_repo(db_factory: Callable[..., Database]) -> CardRepository:
    repo = CardRepository(db_factory())
    with open(FIXTURES_DIR / "scryfall_sample.json") as f:
        cards = [Card.from_scryfall(d) for d in json.load(f)]
    repo.bulk_insert(cards)
    return repo


class TestDeckDiffService:
    def test_diff_without_card_repo(self) -> None:
        svc = DeckDiffService(card_repo=None)
        diff = svc.diff(OLD_STATE, NEW_STATE)
        assert diff.has_changes
        assert diff.stats_delta is None

    def test_diff_detects_added(self) -> None:
        svc = DeckDiffService()
        diff = svc.diff(OLD_STATE, NEW_STATE)
        added = [c for c in diff.changes if c.change_type == ChangeType.ADDED]
        assert any(c.card_name == "Monastery Swiftspear" for c in added)

    def test_diff_detects_removed(self) -> None:
        svc = DeckDiffService()
        diff = svc.diff(OLD_STATE, NEW_STATE)
        removed = [c for c in diff.changes if c.change_type == ChangeType.REMOVED]
        assert any(c.card_name == "Goblin Guide" for c in removed)

    def test_diff_detects_unchanged(self) -> None:
        svc = DeckDiffService()
        diff = svc.diff(OLD_STATE, NEW_STATE)
        unchanged = [c for c in diff.changes if c.change_type == ChangeType.UNCHANGED]
        assert any(c.card_name == "Lightning Bolt" for c in unchanged)

    def test_diff_snapshot_parent_with_none(self) -> None:
        svc = DeckDiffService()
        diff = svc.diff_snapshot_parent(OLD_STATE, parent_state=None)
        # All cards should be "added" since parent is empty
        assert all(
            c.change_type == ChangeType.ADDED for c in diff.changes
        )

    def test_diff_snapshot_parent_with_state(self) -> None:
        svc = DeckDiffService()
        diff = svc.diff_snapshot_parent(NEW_STATE, parent_state=OLD_STATE)
        assert diff.has_changes

    def test_identical_states(self) -> None:
        svc = DeckDiffService()
        diff = svc.diff(OLD_STATE, OLD_STATE)
        assert not diff.has_changes


class TestStatsDelta:
    """Stats-delta computation only runs when a card repository is supplied."""

    def test_stats_delta_present_with_repo(self, card_repo: CardRepository) -> None:
        svc = DeckDiffService(card_repo=card_repo)
        # Goblin Guide (4) -> Lava Spike (4); both cmc 1, totals equal.
        diff = svc.diff("4 Lightning Bolt\n4 Goblin Guide\n", "4 Lightning Bolt\n4 Lava Spike\n")
        assert diff.stats_delta is not None
        assert diff.stats_delta.old_total == 8
        assert diff.stats_delta.new_total == 8

    def test_stats_delta_tracks_total_change(
        self, card_repo: CardRepository
    ) -> None:
        svc = DeckDiffService(card_repo=card_repo)
        diff = svc.diff("4 Lightning Bolt\n", "4 Lightning Bolt\n2 Lava Spike\n")
        assert diff.stats_delta is not None
        assert diff.stats_delta.old_total == 4
        assert diff.stats_delta.new_total == 6

    def test_stats_delta_curve_shift(self, card_repo: CardRepository) -> None:
        svc = DeckDiffService(card_repo=card_repo)
        # cmc 1 -> cmc 2 card swap should register a curve delta.
        diff = svc.diff(
            "4 Lightning Bolt\n",
            "4 Eidolon of the Great Revel\n",
        )
        assert diff.stats_delta is not None
        assert diff.stats_delta.curve_delta  # non-empty

    def test_stats_delta_identical_states_zero_curve(
        self, card_repo: CardRepository
    ) -> None:
        svc = DeckDiffService(card_repo=card_repo)
        diff = svc.diff(OLD_STATE, OLD_STATE)
        assert diff.stats_delta is not None
        assert diff.stats_delta.curve_delta == {}
        assert diff.stats_delta.old_total == diff.stats_delta.new_total

    def test_snapshot_parent_with_repo_and_none_parent(
        self, card_repo: CardRepository
    ) -> None:
        svc = DeckDiffService(card_repo=card_repo)
        diff = svc.diff_snapshot_parent(OLD_STATE, parent_state=None)
        assert diff.stats_delta is not None
        assert diff.stats_delta.old_total == 0
        assert diff.stats_delta.new_total == 8

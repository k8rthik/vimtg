"""Tests for the deck diff service."""

from vimtg.domain.deck import DeckSection
from vimtg.domain.deck_diff import ChangeType
from vimtg.services.deck_diff_service import DeckDiffService


OLD_STATE = "4 Lightning Bolt\n4 Goblin Guide\n"
NEW_STATE = "4 Lightning Bolt\n4 Monastery Swiftspear\n"


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

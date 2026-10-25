"""Tests for the persistent version control service."""

from collections.abc import Callable

import pytest

from vimtg.data.database import Database
from vimtg.data.snapshot_repository import SnapshotRepository
from vimtg.services.vcs_service import VersionControlService, commit_message

DECK_PATH = "/tmp/test.deck"
STATE_V1 = "4 Lightning Bolt\n4 Goblin Guide\n"
STATE_V2 = "4 Lightning Bolt\n4 Goblin Guide\n4 Monastery Swiftspear\n"
STATE_V3 = "4 Lightning Bolt\n4 Goblin Guide\n4 Monastery Swiftspear\n2 Shock\n"


@pytest.fixture
def snapshot_repo(db_factory: Callable[..., Database]) -> SnapshotRepository:
    return SnapshotRepository(db_factory())


@pytest.fixture
def vcs(snapshot_repo: SnapshotRepository) -> VersionControlService:
    return VersionControlService(snapshot_repo, DECK_PATH)


class TestCommit:
    def test_first_commit_has_no_parent(self, vcs: VersionControlService) -> None:
        snap = vcs.commit(STATE_V1, "initial build")
        assert snap.description == "initial build"
        assert snap.parent_id is None

    def test_second_commit_chains_parent(self, vcs: VersionControlService) -> None:
        snap1 = vcs.commit(STATE_V1, "initial")
        snap2 = vcs.commit(STATE_V2, "added swiftspear")
        assert snap2.parent_id == snap1.id

    def test_dedup_skips_identical(self, vcs: VersionControlService) -> None:
        snap1 = vcs.commit(STATE_V1, "initial")
        snap2 = vcs.commit(STATE_V1, "duplicate")
        assert snap1.id == snap2.id  # Same snapshot returned

    def test_commit_names_an_auto_snapshot_of_the_same_deck(
        self, vcs: VersionControlService, snapshot_repo: SnapshotRepository,
    ) -> None:
        """:w snapshots as "auto: save"; a :commit right after it must keep
        the user's message rather than report the auto snapshot."""
        auto = vcs.commit(STATE_V1, "auto: save")
        named = vcs.commit(STATE_V1, "first try")
        assert (named.id, named.description) == (auto.id, "first try")
        stored = snapshot_repo.get_snapshot(auto.id)
        assert stored is not None and stored.description == "first try"

    def test_commit_message_says_nothing_changed(self, vcs: VersionControlService) -> None:
        first = vcs.commit(STATE_V1, "first try")
        again = vcs.commit(STATE_V1, "second")
        assert commit_message(first, "first try") == "Snapshot: first try"
        assert commit_message(again, "second") == (
            "Nothing to commit: the deck matches snapshot 'first try'"
        )

    def test_dedup_allows_different_state(self, vcs: VersionControlService) -> None:
        snap1 = vcs.commit(STATE_V1, "initial")
        snap2 = vcs.commit(STATE_V2, "changed")
        assert snap1.id != snap2.id

    def test_history_continues_across_services(
        self, snapshot_repo: SnapshotRepository
    ) -> None:
        first = VersionControlService(snapshot_repo, DECK_PATH).commit(STATE_V1, "one")
        second = VersionControlService(snapshot_repo, DECK_PATH).commit(STATE_V2, "two")
        assert second.parent_id == first.id

    def test_history_is_scoped_per_deck(
        self, vcs: VersionControlService, snapshot_repo: SnapshotRepository
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        other = VersionControlService(snapshot_repo, "/tmp/other.deck")
        assert other.get_log() == []
        assert other.commit(STATE_V2, "theirs").parent_id is None
        assert [s.description for s in vcs.get_log()] == ["initial"]


class TestGetLog:
    def test_empty_log(self, vcs: VersionControlService) -> None:
        assert vcs.get_log() == []

    def test_log_returns_ancestors(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "first")
        vcs.commit(STATE_V2, "second")
        vcs.commit(STATE_V3, "third")
        log = vcs.get_log()
        assert len(log) == 3
        assert log[0].description == "third"
        assert log[2].description == "first"


class TestCheckoutRestore:
    def test_checkout_returns_state(self, vcs: VersionControlService) -> None:
        snap = vcs.commit(STATE_V1, "initial")
        state = vcs.checkout(snap.id)
        assert state == STATE_V1

    def test_checkout_nonexistent(self, vcs: VersionControlService) -> None:
        assert vcs.checkout("nonexistent") is None

    def test_restore_creates_new_commit(self, vcs: VersionControlService) -> None:
        snap1 = vcs.commit(STATE_V1, "initial")
        vcs.commit(STATE_V2, "changed")
        restored = vcs.restore(snap1.id)
        assert restored is not None
        assert restored.deck_state == STATE_V1
        assert restored.description == "restore: initial"
        # Should be a new snapshot, not the original
        log = vcs.get_log()
        assert len(log) == 3

    def test_restore_nonexistent(self, vcs: VersionControlService) -> None:
        assert vcs.restore("nonexistent") is None


class TestIsDirty:
    def test_dirty_with_no_commits(self, vcs: VersionControlService) -> None:
        assert vcs.is_dirty(STATE_V1) is True

    def test_clean_at_tip(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        assert vcs.is_dirty(STATE_V1) is False

    def test_dirty_when_changed(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        assert vcs.is_dirty(STATE_V2) is True


class TestTags:
    def test_tag_snapshot(self, vcs: VersionControlService) -> None:
        snap = vcs.commit(STATE_V1, "initial")
        assert vcs.tag(snap.id, "FNM-2025") is True
        log = vcs.get_log()
        assert log[0].tag == "FNM-2025"

    def test_untag_snapshot(self, vcs: VersionControlService) -> None:
        snap = vcs.commit(STATE_V1, "initial")
        vcs.tag(snap.id, "FNM-2025")
        assert vcs.untag(snap.id) is True
        log = vcs.get_log()
        assert log[0].tag is None

    def test_tag_nonexistent(self, vcs: VersionControlService) -> None:
        assert vcs.tag("nonexistent", "tag") is False

    def test_untag_nonexistent(self, vcs: VersionControlService) -> None:
        assert vcs.untag("nonexistent") is False


class TestStatus:
    def test_status_with_no_history(self, vcs: VersionControlService) -> None:
        status = vcs.status(STATE_V1)
        assert status.snapshot_count == 0
        assert status.has_uncommitted_changes is True

    def test_status_after_commit(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        status = vcs.status(STATE_V1)
        assert status.snapshot_count == 1
        assert status.has_uncommitted_changes is False
        assert status.last_snapshot_description == "initial"

    def test_status_with_uncommitted_changes(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        status = vcs.status(STATE_V2)
        assert status.has_uncommitted_changes is True


class TestIsDirtySemanticFallback:
    def test_scaffolded_metadata_is_not_dirty(
        self, vcs: VersionControlService
    ) -> None:
        """Cosmetic drift (scaffolded empty metadata lines) must not show
        up as uncommitted changes."""
        vcs.commit(STATE_V1, "initial")
        scaffolded = "// Tags:\n\n" + STATE_V1
        assert vcs.is_dirty(scaffolded) is False

    def test_card_change_is_dirty(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        assert vcs.is_dirty(STATE_V1.replace("4 Lightning", "2 Lightning")) is True

    def test_metadata_value_change_is_dirty(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit("// Format: modern\n\n" + STATE_V1, "initial")
        assert vcs.is_dirty("// Format: legacy\n\n" + STATE_V1) is True


class TestIsDirtyPlans:
    def test_plan_edit_is_dirty(self, vcs: VersionControlService) -> None:
        with_plan = STATE_V1 + "\nVS: Tron\n    -1 Goblin Guide\n"
        vcs.commit(with_plan, "initial")
        assert vcs.is_dirty(with_plan.replace("-1 Goblin", "-2 Goblin")) is True

    def test_new_plan_is_dirty(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        assert vcs.is_dirty(STATE_V1 + "\nVS: Tron\n") is True

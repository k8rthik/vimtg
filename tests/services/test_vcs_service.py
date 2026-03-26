"""Tests for the persistent version control service."""

from pathlib import Path

import pytest

from vimtg.data.database import Database
from vimtg.data.snapshot_repository import SnapshotRepository
from vimtg.services.vcs_service import VersionControlService


DECK_PATH = "/tmp/test.deck"
STATE_V1 = "4 Lightning Bolt\n4 Goblin Guide\n"
STATE_V2 = "4 Lightning Bolt\n4 Goblin Guide\n4 Monastery Swiftspear\n"
STATE_V3 = "4 Lightning Bolt\n4 Goblin Guide\n4 Monastery Swiftspear\n2 Shock\n"
STATE_BUDGET = "4 Shock\n4 Lava Spike\n"


@pytest.fixture
def vcs(tmp_db: Path) -> VersionControlService:
    db = Database(tmp_db)
    db.initialize()
    repo = SnapshotRepository(db)
    return VersionControlService(repo, DECK_PATH)


class TestCommit:
    def test_first_commit_creates_branch(self, vcs: VersionControlService) -> None:
        snap = vcs.commit(STATE_V1, "initial build")
        assert snap.description == "initial build"
        assert snap.branch == "main"
        assert snap.parent_id is None
        branches = vcs.list_branches()
        assert len(branches) == 1
        assert branches[0].name == "main"

    def test_second_commit_chains_parent(self, vcs: VersionControlService) -> None:
        snap1 = vcs.commit(STATE_V1, "initial")
        snap2 = vcs.commit(STATE_V2, "added swiftspear")
        assert snap2.parent_id == snap1.id

    def test_dedup_skips_identical(self, vcs: VersionControlService) -> None:
        snap1 = vcs.commit(STATE_V1, "initial")
        snap2 = vcs.commit(STATE_V1, "duplicate")
        assert snap1.id == snap2.id  # Same snapshot returned

    def test_dedup_allows_different_state(self, vcs: VersionControlService) -> None:
        snap1 = vcs.commit(STATE_V1, "initial")
        snap2 = vcs.commit(STATE_V2, "changed")
        assert snap1.id != snap2.id


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

    def test_log_for_specific_branch(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "main commit")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        vcs.commit(STATE_BUDGET, "budget build")
        log = vcs.get_log(branch="budget")
        assert len(log) == 2  # budget commit + shared initial
        assert log[0].description == "budget build"


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


class TestBranches:
    def test_create_branch(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        branch = vcs.create_branch("budget")
        assert branch is not None
        assert branch.name == "budget"

    def test_create_duplicate_branch_fails(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        assert vcs.create_branch("budget") is None

    def test_create_branch_without_snapshots_fails(self, vcs: VersionControlService) -> None:
        assert vcs.create_branch("budget") is None

    def test_switch_branch(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        vcs.commit(STATE_BUDGET, "budget build")
        state = vcs.switch_branch("main")
        assert state == STATE_V1
        assert vcs.current_branch == "main"

    def test_switch_nonexistent_branch(self, vcs: VersionControlService) -> None:
        assert vcs.switch_branch("nonexistent") is None

    def test_list_branches(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.create_branch("tournament")
        branches = vcs.list_branches()
        names = [b.name for b in branches]
        assert "main" in names
        assert "budget" in names
        assert "tournament" in names

    def test_delete_branch(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        assert vcs.delete_branch("budget") is True
        branches = vcs.list_branches()
        names = [b.name for b in branches]
        assert "budget" not in names

    def test_cannot_delete_current_branch(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        assert vcs.delete_branch("main") is False

    def test_delete_nonexistent_branch(self, vcs: VersionControlService) -> None:
        assert vcs.delete_branch("nonexistent") is False


class TestMerge:
    def test_merge_branch(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        vcs.commit(STATE_BUDGET, "budget build")
        vcs.switch_branch("main")
        diff = vcs.merge_branch("budget")
        assert diff is not None
        assert diff.has_changes

    def test_merge_nonexistent_branch(self, vcs: VersionControlService) -> None:
        assert vcs.merge_branch("nonexistent") is None


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


class TestCherryPick:
    def test_cherry_pick_adds_card(self, vcs: VersionControlService) -> None:
        # Set up: main has v1 -> v2 (adds swiftspear) -> v3 (adds shock)
        vcs.commit(STATE_V1, "initial")
        vcs.commit(STATE_V2, "added swiftspear")
        snap3 = vcs.commit(STATE_V3, "added shock")
        # Create "other" branch forked from main tip (which has v3)
        # Then switch to other and commit a different state that lacks shock
        vcs.create_branch("other")
        vcs.switch_branch("other")
        # Commit a state without shock on the other branch
        other_state = "4 Lightning Bolt\n4 Goblin Guide\n4 Monastery Swiftspear\n4 Lava Spike\n"
        vcs.commit(other_state, "other branch diverged")
        # Now cherry-pick snap3 (which added shock) onto other branch
        diff = vcs.cherry_pick(snap3.id)
        assert diff is not None
        log = vcs.get_log()
        assert "cherry-pick" in log[0].description

    def test_cherry_pick_nonexistent(self, vcs: VersionControlService) -> None:
        assert vcs.cherry_pick("nonexistent") is None


class TestSquash:
    def test_squash_multiple(self, vcs: VersionControlService) -> None:
        snap1 = vcs.commit(STATE_V1, "first")
        snap2 = vcs.commit(STATE_V2, "second")
        snap3 = vcs.commit(STATE_V3, "third")
        result = vcs.squash([snap1.id, snap2.id, snap3.id], "squashed")
        assert result is not None
        assert result.description == "squashed"
        assert result.deck_state == STATE_V3  # final state

    def test_squash_empty_list(self, vcs: VersionControlService) -> None:
        assert vcs.squash([], "empty") is None

    def test_squash_nonexistent(self, vcs: VersionControlService) -> None:
        assert vcs.squash(["nonexistent"], "fail") is None


class TestStatus:
    def test_status_with_no_history(self, vcs: VersionControlService) -> None:
        status = vcs.status(STATE_V1)
        assert status.branch == "main"
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

    def test_status_on_branch(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        status = vcs.status(STATE_V1)
        assert status.branch == "budget"

"""Tests for the persistent version control service."""

from collections.abc import Callable

import pytest

from vimtg.data.database import Database
from vimtg.data.snapshot_repository import SnapshotRepository
from vimtg.domain.deck import DeckSection
from vimtg.services.vcs_service import MergeKind, VersionControlService

DECK_PATH = "/tmp/test.deck"
STATE_V1 = "4 Lightning Bolt\n4 Goblin Guide\n"
STATE_V2 = "4 Lightning Bolt\n4 Goblin Guide\n4 Monastery Swiftspear\n"
STATE_V3 = "4 Lightning Bolt\n4 Goblin Guide\n4 Monastery Swiftspear\n2 Shock\n"
STATE_BUDGET = "4 Shock\n4 Lava Spike\n"


@pytest.fixture
def snapshot_repo(db_factory: Callable[..., Database]) -> SnapshotRepository:
    return SnapshotRepository(db_factory())


@pytest.fixture
def vcs(snapshot_repo: SnapshotRepository) -> VersionControlService:
    return VersionControlService(snapshot_repo, DECK_PATH)


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


def _diverge(vcs: VersionControlService) -> None:
    """main: V1 -> +Swiftspear; budget (from V1): +Chandra."""
    vcs.commit(STATE_V1, "initial")
    vcs.create_branch("budget")
    vcs.switch_branch("budget")
    vcs.commit(STATE_V1 + "2 Chandra, Torch of Defiance\n", "add chandra")
    vcs.switch_branch("main")
    vcs.commit(STATE_V2, "add swiftspear")


class TestMerge:
    def test_merge_nonexistent_branch(self, vcs: VersionControlService) -> None:
        result = vcs.merge_branch("nonexistent")
        assert result.kind is MergeKind.FAILED

    def test_merge_self_is_up_to_date(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        result = vcs.merge_branch("main")
        assert result.kind is MergeKind.UP_TO_DATE

    def test_merge_ancestor_is_up_to_date(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.commit(STATE_V2, "main moved ahead")
        result = vcs.merge_branch("budget")
        assert result.kind is MergeKind.UP_TO_DATE

    def test_merge_descendant_fast_forwards(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        tip = vcs.commit(STATE_V2, "budget moved ahead")
        vcs.switch_branch("main")
        result = vcs.merge_branch("budget")
        assert result.kind is MergeKind.FAST_FORWARD
        assert result.new_state == STATE_V2
        # Ref moved, no new commit
        log = vcs.get_log()
        assert log[0].id == tip.id
        assert log[0].merge_parent_id is None

    def test_diamond_auto_merge_creates_merge_commit(
        self, vcs: VersionControlService
    ) -> None:
        _diverge(vcs)
        result = vcs.merge_branch("budget")
        assert result.kind is MergeKind.MERGED
        assert result.new_state is not None
        assert "Monastery Swiftspear" in result.new_state
        assert "Chandra, Torch of Defiance" in result.new_state
        assert result.snapshot is not None
        assert result.snapshot.parent_id is not None
        assert result.snapshot.merge_parent_id is not None
        # After the merge, budget is fully contained: re-merge is a no-op
        assert vcs.merge_branch("budget").kind is MergeKind.UP_TO_DATE

    def test_log_after_merge_walks_first_parent(
        self, vcs: VersionControlService
    ) -> None:
        _diverge(vcs)
        vcs.merge_branch("budget")
        log = vcs.get_log()
        descriptions = [s.description for s in log]
        assert descriptions[0].startswith("merge: budget")
        assert "add swiftspear" in descriptions  # first-parent side
        assert "add chandra" not in descriptions  # second-parent side hidden

    def test_conflicting_merge_returns_pending(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        vcs.commit("2 Lightning Bolt\n4 Goblin Guide\n", "trim bolts")
        vcs.switch_branch("main")
        vcs.commit("1 Lightning Bolt\n4 Goblin Guide\n", "one bolt")
        result = vcs.merge_branch("budget")
        assert result.kind is MergeKind.CONFLICTS
        assert result.pending is not None
        (conflict,) = result.pending.conflicts
        assert conflict.card_name == "Lightning Bolt"
        assert conflict.ours_quantity == 1
        assert conflict.theirs_quantity == 2
        # Nothing committed yet
        assert vcs.get_log()[0].description == "one bolt"

    def test_merge_into_unborn_branch_fast_forwards(
        self, snapshot_repo: SnapshotRepository
    ) -> None:
        vcs = VersionControlService(snapshot_repo, DECK_PATH)
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        vcs.commit(STATE_V2, "work")
        vcs.delete_branch("main")
        snapshot_repo.set_head(DECK_PATH, "main")
        vcs2 = VersionControlService(snapshot_repo, DECK_PATH)
        assert vcs2.current_branch == "main"  # unborn: no branch row exists
        result = vcs2.merge_branch("budget")
        assert result.kind is MergeKind.FAST_FORWARD
        assert result.new_state == STATE_V2


class TestCompleteMerge:
    def _conflicted(self, vcs: VersionControlService) -> object:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        vcs.commit("2 Lightning Bolt\n4 Goblin Guide\n", "trim bolts")
        vcs.switch_branch("main")
        vcs.commit("1 Lightning Bolt\n4 Goblin Guide\n", "one bolt")
        result = vcs.merge_branch("budget")
        assert result.pending is not None
        return result.pending

    def test_resolutions_produce_merge_commit(
        self, vcs: VersionControlService
    ) -> None:
        pending = self._conflicted(vcs)
        result = vcs.complete_merge(
            pending,  # type: ignore[arg-type]
            {("Lightning Bolt", DeckSection.MAIN): 3},
        )
        assert result.kind is MergeKind.MERGED
        assert result.new_state is not None
        assert "3 Lightning Bolt" in result.new_state
        assert result.snapshot is not None
        assert result.snapshot.merge_parent_id is not None

    def test_none_resolution_omits_card(
        self, vcs: VersionControlService
    ) -> None:
        pending = self._conflicted(vcs)
        result = vcs.complete_merge(
            pending,  # type: ignore[arg-type]
            {("Lightning Bolt", DeckSection.MAIN): None},
        )
        assert result.kind is MergeKind.MERGED
        assert result.new_state is not None
        assert "Lightning Bolt" not in result.new_state

    def test_missing_resolution_fails(
        self, vcs: VersionControlService
    ) -> None:
        pending = self._conflicted(vcs)
        result = vcs.complete_merge(pending, {})  # type: ignore[arg-type]
        assert result.kind is MergeKind.FAILED


class TestMergeExternal:
    def test_disjoint_decks_union(self, vcs: VersionControlService) -> None:
        vcs.commit(STATE_V1, "initial")
        result = vcs.merge_external(STATE_BUDGET, "burn.deck")
        assert result.kind is MergeKind.MERGED
        assert result.new_state is not None
        assert "Lightning Bolt" in result.new_state
        assert "Lava Spike" in result.new_state
        assert result.snapshot is not None
        assert result.snapshot.merge_parent_id is None

    def test_same_quantity_overlap_is_clean(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        result = vcs.merge_external(
            "4 Lightning Bolt\n2 Shock\n", "other.deck"
        )
        assert result.kind is MergeKind.MERGED

    def test_different_quantity_overlap_conflicts(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        result = vcs.merge_external("2 Lightning Bolt\n", "other.deck")
        assert result.kind is MergeKind.CONFLICTS
        assert result.pending is not None
        assert result.pending.theirs_tip_id is None

    def test_identical_deck_nothing_to_merge(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        result = vcs.merge_external(STATE_V1, "copy.deck")
        assert result.kind is MergeKind.UP_TO_DATE
        assert len(vcs.get_log()) == 1


class TestRebase:
    def test_rebase_replays_onto_target(
        self, vcs: VersionControlService
    ) -> None:
        _diverge(vcs)
        vcs.switch_branch("budget")
        old_tip = vcs.get_log()[0]
        result = vcs.rebase("main")
        assert result.kind is MergeKind.MERGED
        assert result.replayed == 1
        assert result.new_state is not None
        assert "Monastery Swiftspear" in result.new_state
        assert "Chandra, Torch of Defiance" in result.new_state
        log = vcs.get_log()
        assert log[0].description == "add chandra"  # description preserved
        assert log[0].id != old_tip.id  # new snapshot id
        assert log[1].description == "add swiftspear"  # now atop main
        # Original still fetchable by id, but absent from the log
        assert vcs.checkout(old_tip.id) is not None
        assert old_tip.id not in [s.id for s in log]

    def test_rebase_onto_missing_branch_fails(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        assert vcs.rebase("nonexistent").kind is MergeKind.FAILED

    def test_rebase_onto_self_up_to_date(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        assert vcs.rebase("main").kind is MergeKind.UP_TO_DATE

    def test_rebase_onto_ancestor_up_to_date(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.commit(STATE_V2, "ahead")
        assert vcs.rebase("budget").kind is MergeKind.UP_TO_DATE

    def test_rebase_behind_target_fast_forwards(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.commit(STATE_V2, "main ahead")
        vcs.switch_branch("budget")
        result = vcs.rebase("main")
        assert result.kind is MergeKind.FAST_FORWARD
        assert result.new_state == STATE_V2

    def test_rebase_skips_empty_replays(
        self, vcs: VersionControlService
    ) -> None:
        # budget's only change is one main already has: replay is a no-op
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        vcs.commit(STATE_V2, "same as main will have")
        vcs.switch_branch("main")
        vcs.commit(STATE_V2, "main does the same thing")
        vcs.commit(STATE_V3, "and more")
        vcs.switch_branch("budget")
        result = vcs.rebase("main")
        assert result.kind is MergeKind.MERGED
        assert result.replayed == 0
        assert result.skipped == 1
        assert result.new_state == STATE_V3  # pure fast-forward-with-drop

    def test_rebase_overlap_replayed_wins(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        vcs.commit("2 Lightning Bolt\n4 Goblin Guide\n", "two bolts")
        vcs.switch_branch("main")
        vcs.commit("1 Lightning Bolt\n4 Goblin Guide\n", "one bolt")
        vcs.switch_branch("budget")
        result = vcs.rebase("main")
        assert result.kind is MergeKind.MERGED
        assert result.new_state is not None
        assert "2 Lightning Bolt" in result.new_state


class TestPersistedHead:
    def test_head_survives_new_service(
        self, snapshot_repo: SnapshotRepository
    ) -> None:
        vcs = VersionControlService(snapshot_repo, DECK_PATH)
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        vcs2 = VersionControlService(snapshot_repo, DECK_PATH)
        assert vcs2.current_branch == "budget"

    def test_default_head_is_main(
        self, snapshot_repo: SnapshotRepository
    ) -> None:
        vcs = VersionControlService(snapshot_repo, DECK_PATH)
        assert vcs.current_branch == "main"

    def test_stale_head_falls_back_to_main(
        self, snapshot_repo: SnapshotRepository
    ) -> None:
        snapshot_repo.set_head(DECK_PATH, "deleted-branch")
        vcs = VersionControlService(snapshot_repo, DECK_PATH)
        assert vcs.current_branch == "main"

    def test_heads_scoped_per_deck(
        self, snapshot_repo: SnapshotRepository
    ) -> None:
        vcs = VersionControlService(snapshot_repo, DECK_PATH)
        vcs.commit(STATE_V1, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        other = VersionControlService(snapshot_repo, "/tmp/other.deck")
        assert other.current_branch == "main"


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


class TestIsDirtySemanticFallback:
    def test_scaffolded_metadata_is_not_dirty(
        self, vcs: VersionControlService
    ) -> None:
        """Cosmetic drift (scaffolded empty metadata lines) must not lock
        the user out of merge/rebase/switch."""
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

"""Tests for the persistent snapshot repository."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from vimtg.data.database import Database
from vimtg.data.snapshot_repository import SnapshotRepository
from vimtg.domain.vcs import VCSBranch, VCSSnapshot


DECK_PATH = "/tmp/test.deck"


@pytest.fixture
def repo(tmp_db: Path) -> SnapshotRepository:
    db = Database(tmp_db)
    db.initialize()
    return SnapshotRepository(db)


def _snap(
    id: str = "snap1",
    parent_id: str | None = None,
    deck_state: str = "4 Lightning Bolt\n",
    description: str = "test",
    branch: str = "main",
    tag: str | None = None,
    deck_hash: str = "abc123",
    timestamp: datetime | None = None,
) -> VCSSnapshot:
    return VCSSnapshot(
        id=id,
        deck_path=DECK_PATH,
        parent_id=parent_id,
        deck_state=deck_state,
        timestamp=timestamp or datetime(2025, 3, 15, 14, 30, tzinfo=UTC),
        description=description,
        branch=branch,
        tag=tag,
        deck_hash=deck_hash,
    )


class TestSaveAndGet:
    def test_save_and_get(self, repo: SnapshotRepository) -> None:
        snap = _snap()
        repo.save_snapshot(snap)
        result = repo.get_snapshot("snap1")
        assert result is not None
        assert result.id == "snap1"
        assert result.deck_state == "4 Lightning Bolt\n"
        assert result.branch == "main"
        assert result.deck_hash == "abc123"

    def test_get_nonexistent(self, repo: SnapshotRepository) -> None:
        assert repo.get_snapshot("nonexistent") is None

    def test_tag_preserved(self, repo: SnapshotRepository) -> None:
        snap = _snap(tag="FNM-2025")
        repo.save_snapshot(snap)
        result = repo.get_snapshot("snap1")
        assert result is not None
        assert result.tag == "FNM-2025"


class TestListSnapshots:
    def test_list_empty(self, repo: SnapshotRepository) -> None:
        assert repo.list_snapshots(DECK_PATH) == []

    def test_list_ordered_by_timestamp_desc(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(
            id="old", timestamp=datetime(2025, 1, 1, tzinfo=UTC),
        ))
        repo.save_snapshot(_snap(
            id="new", timestamp=datetime(2025, 6, 1, tzinfo=UTC),
        ))
        result = repo.list_snapshots(DECK_PATH)
        assert [s.id for s in result] == ["new", "old"]

    def test_list_filtered_by_branch(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(id="main1", branch="main"))
        repo.save_snapshot(_snap(id="budget1", branch="budget"))
        result = repo.list_snapshots(DECK_PATH, branch="budget")
        assert len(result) == 1
        assert result[0].id == "budget1"

    def test_list_limited(self, repo: SnapshotRepository) -> None:
        for i in range(10):
            repo.save_snapshot(_snap(
                id=f"snap{i}",
                timestamp=datetime(2025, 1, 1 + i, tzinfo=UTC),
            ))
        result = repo.list_snapshots(DECK_PATH, limit=3)
        assert len(result) == 3

    def test_list_different_deck_path(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(id="snap1"))
        result = repo.list_snapshots("/tmp/other.deck")
        assert result == []


class TestAncestors:
    def test_linear_chain(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(id="root"))
        repo.save_snapshot(_snap(id="child1", parent_id="root"))
        repo.save_snapshot(_snap(id="child2", parent_id="child1"))
        ancestors = repo.get_ancestors("child2")
        assert [a.id for a in ancestors] == ["child2", "child1", "root"]

    def test_single_node(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(id="root"))
        ancestors = repo.get_ancestors("root")
        assert len(ancestors) == 1
        assert ancestors[0].id == "root"

    def test_limit(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(id="root"))
        repo.save_snapshot(_snap(id="child1", parent_id="root"))
        repo.save_snapshot(_snap(id="child2", parent_id="child1"))
        ancestors = repo.get_ancestors("child2", limit=2)
        assert len(ancestors) == 2

    def test_nonexistent_id(self, repo: SnapshotRepository) -> None:
        assert repo.get_ancestors("nonexistent") == []


class TestTags:
    def test_update_tag(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap())
        repo.update_snapshot_tag("snap1", "tournament-v1")
        result = repo.get_snapshot("snap1")
        assert result is not None
        assert result.tag == "tournament-v1"

    def test_clear_tag(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(tag="old-tag"))
        repo.update_snapshot_tag("snap1", None)
        result = repo.get_snapshot("snap1")
        assert result is not None
        assert result.tag is None


class TestSnapshotCount:
    def test_empty(self, repo: SnapshotRepository) -> None:
        assert repo.snapshot_count(DECK_PATH) == 0

    def test_count(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(id="a"))
        repo.save_snapshot(_snap(id="b"))
        repo.save_snapshot(_snap(id="c"))
        assert repo.snapshot_count(DECK_PATH) == 3

    def test_count_scoped_to_deck_path(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(id="a"))
        assert repo.snapshot_count("/tmp/other.deck") == 0


class TestDeleteSnapshots:
    def test_delete_by_ids(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(id="a"))
        repo.save_snapshot(_snap(id="b"))
        repo.save_snapshot(_snap(id="c"))
        repo.delete_snapshots_by_ids(["a", "c"])
        assert repo.get_snapshot("a") is None
        assert repo.get_snapshot("b") is not None
        assert repo.get_snapshot("c") is None

    def test_delete_empty_list(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(id="a"))
        repo.delete_snapshots_by_ids([])
        assert repo.get_snapshot("a") is not None


class TestBranches:
    def test_save_and_get_branch(self, repo: SnapshotRepository) -> None:
        branch = VCSBranch(
            name="budget",
            deck_path=DECK_PATH,
            tip_id="snap1",
            created_at=datetime(2025, 3, 15, tzinfo=UTC),
        )
        repo.save_branch(branch)
        result = repo.get_branch(DECK_PATH, "budget")
        assert result is not None
        assert result.name == "budget"
        assert result.tip_id == "snap1"

    def test_get_nonexistent_branch(self, repo: SnapshotRepository) -> None:
        assert repo.get_branch(DECK_PATH, "nonexistent") is None

    def test_list_branches(self, repo: SnapshotRepository) -> None:
        for name in ("main", "budget", "tournament"):
            repo.save_branch(VCSBranch(
                name=name,
                deck_path=DECK_PATH,
                tip_id="snap1",
                created_at=datetime(2025, 3, 15, tzinfo=UTC),
            ))
        result = repo.list_branches(DECK_PATH)
        names = [b.name for b in result]
        assert names == ["budget", "main", "tournament"]  # sorted

    def test_list_branches_scoped_to_deck(self, repo: SnapshotRepository) -> None:
        repo.save_branch(VCSBranch(
            name="main",
            deck_path=DECK_PATH,
            tip_id="snap1",
            created_at=datetime(2025, 3, 15, tzinfo=UTC),
        ))
        assert repo.list_branches("/tmp/other.deck") == []

    def test_delete_branch(self, repo: SnapshotRepository) -> None:
        repo.save_branch(VCSBranch(
            name="budget",
            deck_path=DECK_PATH,
            tip_id="snap1",
            created_at=datetime(2025, 3, 15, tzinfo=UTC),
        ))
        repo.delete_branch(DECK_PATH, "budget")
        assert repo.get_branch(DECK_PATH, "budget") is None

    def test_update_branch_tip(self, repo: SnapshotRepository) -> None:
        repo.save_branch(VCSBranch(
            name="main",
            deck_path=DECK_PATH,
            tip_id="snap1",
            created_at=datetime(2025, 3, 15, tzinfo=UTC),
        ))
        repo.update_branch_tip(DECK_PATH, "main", "snap2")
        result = repo.get_branch(DECK_PATH, "main")
        assert result is not None
        assert result.tip_id == "snap2"

    def test_save_branch_upserts(self, repo: SnapshotRepository) -> None:
        branch = VCSBranch(
            name="main",
            deck_path=DECK_PATH,
            tip_id="snap1",
            created_at=datetime(2025, 3, 15, tzinfo=UTC),
        )
        repo.save_branch(branch)
        updated = VCSBranch(
            name="main",
            deck_path=DECK_PATH,
            tip_id="snap2",
            created_at=datetime(2025, 3, 16, tzinfo=UTC),
        )
        repo.save_branch(updated)
        result = repo.get_branch(DECK_PATH, "main")
        assert result is not None
        assert result.tip_id == "snap2"
        assert len(repo.list_branches(DECK_PATH)) == 1

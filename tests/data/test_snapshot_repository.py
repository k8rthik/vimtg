"""Tests for the persistent snapshot repository."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from vimtg.data.database import Database
from vimtg.data.snapshot_repository import SnapshotRepository
from vimtg.domain.vcs import VCSSnapshot

DECK_PATH = "/tmp/test.deck"


@pytest.fixture
def repo(db_factory: Callable[..., Database]) -> SnapshotRepository:
    return SnapshotRepository(db_factory())


def _snap(
    id: str = "snap1",
    parent_id: str | None = None,
    deck_state: str = "4 Lightning Bolt\n",
    description: str = "test",
    tag: str | None = None,
    deck_hash: str = "abc123",
    timestamp: datetime | None = None,
    deck_path: str = DECK_PATH,
) -> VCSSnapshot:
    return VCSSnapshot(
        id=id,
        deck_path=deck_path,
        parent_id=parent_id,
        deck_state=deck_state,
        timestamp=timestamp or datetime(2025, 3, 15, 14, 30, tzinfo=UTC),
        description=description,
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


class TestTip:
    def test_none_before_first_commit(self, repo: SnapshotRepository) -> None:
        assert repo.tip(DECK_PATH) is None

    def test_end_of_chain(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(id="a"))
        repo.save_snapshot(_snap(id="b", parent_id="a"))
        repo.save_snapshot(_snap(id="c", parent_id="b"))
        tip = repo.tip(DECK_PATH)
        assert tip is not None and tip.id == "c"

    def test_clock_step_does_not_move_the_tip(self, repo: SnapshotRepository) -> None:
        """A save stamped earlier than its parent (the clock stepped back
        between two saves) is still the tip: the chain, not the clock,
        says what is newest."""
        repo.save_snapshot(_snap(id="a", timestamp=datetime(2025, 6, 1, tzinfo=UTC)))
        repo.save_snapshot(_snap(
            id="b", parent_id="a", timestamp=datetime(2025, 5, 1, tzinfo=UTC),
        ))
        tip = repo.tip(DECK_PATH)
        assert tip is not None and tip.id == "b"

    def test_several_leaves_pick_the_newest(self, repo: SnapshotRepository) -> None:
        """A database upgraded from branched history may hold more than
        one chain end; the most recent one continues."""
        repo.save_snapshot(_snap(id="root"))
        repo.save_snapshot(_snap(
            id="old-leaf", parent_id="root", timestamp=datetime(2025, 1, 1, tzinfo=UTC),
        ))
        repo.save_snapshot(_snap(
            id="new-leaf", parent_id="root", timestamp=datetime(2025, 2, 1, tzinfo=UTC),
        ))
        tip = repo.tip(DECK_PATH)
        assert tip is not None and tip.id == "new-leaf"

    def test_scoped_to_deck_path(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap(id="a"))
        assert repo.tip("/tmp/other.deck") is None


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


class TestTimestampsAlwaysCompare:
    def test_naive_and_garbage_rows_load_beside_aware_ones(
        self, repo: SnapshotRepository
    ) -> None:
        repo.save_snapshot(_snap(id="a"))
        repo.save_snapshot(_snap(id="b", parent_id="a", timestamp=datetime(2026, 9, 1)))  # naive
        repo.save_snapshot(_snap(id="c", parent_id="b"))
        conn = repo._db.connect()
        conn.execute("UPDATE snapshots SET timestamp = 'garbage' WHERE id = 'a'")
        conn.commit()
        history = repo.get_ancestors("c")
        assert [s.id for s in history] == ["c", "b", "a"]
        assert all(s.timestamp.tzinfo is not None for s in history)
        tip = repo.tip(DECK_PATH)
        assert tip is not None and tip.id == "c"

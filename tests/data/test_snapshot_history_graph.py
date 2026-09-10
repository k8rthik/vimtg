"""get_history walks both parents so merged-in commits appear in the log."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from vimtg.data.database import Database
from vimtg.data.snapshot_repository import SnapshotRepository
from vimtg.domain.vcs import VCSSnapshot

DECK_PATH = "/tmp/graph.deck"
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def repo(db_factory: Callable[..., Database]) -> SnapshotRepository:
    return SnapshotRepository(db_factory())


def _snap(
    id: str,
    parent_id: str | None,
    minutes: int,
    branch: str = "main",
    merge_parent_id: str | None = None,
    deck_path: str = DECK_PATH,
) -> VCSSnapshot:
    return VCSSnapshot(
        id=id,
        deck_path=deck_path,
        parent_id=parent_id,
        deck_state="4 Lightning Bolt\n",
        timestamp=T0 + timedelta(minutes=minutes),
        description=id,
        branch=branch,
        tag=None,
        deck_hash=id,
        merge_parent_id=merge_parent_id,
    )


def _build_merge_graph(repo: SnapshotRepository) -> None:
    #  root ── a ── merge (main)
    #     └── b ──┘   (budget)
    repo.save_snapshot(_snap("root", None, 0))
    repo.save_snapshot(_snap("a", "root", 1))
    repo.save_snapshot(_snap("b", "root", 2, branch="budget"))
    repo.save_snapshot(_snap("merge", "a", 3, merge_parent_id="b"))


class TestGetHistory:
    def test_includes_merged_in_commits(self, repo: SnapshotRepository) -> None:
        _build_merge_graph(repo)
        ids = [s.id for s in repo.get_history("merge", DECK_PATH)]
        assert set(ids) == {"root", "a", "b", "merge"}

    def test_newest_first_and_tip_first(self, repo: SnapshotRepository) -> None:
        _build_merge_graph(repo)
        ids = [s.id for s in repo.get_history("merge", DECK_PATH)]
        assert ids == ["merge", "b", "a", "root"]

    def test_first_parent_walk_is_unchanged(self, repo: SnapshotRepository) -> None:
        _build_merge_graph(repo)
        ids = [s.id for s in repo.get_ancestors("merge")]
        assert ids == ["merge", "a", "root"]

    def test_limit_caps_result(self, repo: SnapshotRepository) -> None:
        _build_merge_graph(repo)
        assert len(repo.get_history("merge", DECK_PATH, limit=2)) == 2

    def test_never_crosses_deck_partition(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap("other", None, 0, deck_path="/tmp/other.deck"))
        repo.save_snapshot(_snap("tip", "other", 1))
        ids = [s.id for s in repo.get_history("tip", DECK_PATH)]
        assert ids == ["tip"]

    def test_tip_first_even_with_clock_skew(self, repo: SnapshotRepository) -> None:
        repo.save_snapshot(_snap("root", None, 0))
        repo.save_snapshot(_snap("late", "root", 50, branch="budget"))
        repo.save_snapshot(_snap("merge", "root", 3, merge_parent_id="late"))
        ids = [s.id for s in repo.get_history("merge", DECK_PATH)]
        assert ids == ["merge", "late", "root"]

    def test_missing_tip_is_empty(self, repo: SnapshotRepository) -> None:
        assert repo.get_history("nope", DECK_PATH) == []

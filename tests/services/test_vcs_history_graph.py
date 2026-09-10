"""VersionControlService.get_history shows the whole merged graph."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from vimtg.data.database import Database
from vimtg.data.snapshot_repository import SnapshotRepository
from vimtg.services.vcs_service import MergeKind, VersionControlService

DECK_PATH = "/tmp/hist.deck"
BASE = "4 Lightning Bolt\n"
OURS = BASE + "4 Goblin Guide\n"
THEIRS = BASE + "4 Monastery Swiftspear\n"


@pytest.fixture
def vcs(db_factory: Callable[..., Database]) -> VersionControlService:
    return VersionControlService(SnapshotRepository(db_factory()), DECK_PATH)


def _merged(vcs: VersionControlService) -> None:
    vcs.commit(BASE, "base")
    vcs.create_branch("budget")
    vcs.commit(OURS, "ours on main")
    vcs.switch_branch("budget")
    vcs.commit(THEIRS, "theirs on budget")
    vcs.switch_branch("main")
    result = vcs.merge_branch("budget")
    assert result.kind is MergeKind.MERGED


class TestGetHistory:
    def test_empty_when_nothing_committed(self, vcs: VersionControlService) -> None:
        assert vcs.get_history() == []

    def test_log_hides_merged_branch_but_history_shows_it(
        self, vcs: VersionControlService
    ) -> None:
        _merged(vcs)
        log_descs = {s.description for s in vcs.get_log()}
        hist_descs = {s.description for s in vcs.get_history()}
        assert "theirs on budget" not in log_descs
        assert "theirs on budget" in hist_descs
        assert hist_descs >= log_descs

    def test_history_tip_is_first(self, vcs: VersionControlService) -> None:
        _merged(vcs)
        history = vcs.get_history()
        assert history[0].merge_parent_id is not None
        assert history[0].id == vcs.get_log()[0].id

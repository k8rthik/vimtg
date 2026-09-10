"""Fixtures shared by the TUI tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.tui.history_support import DECK_PATH, STATE_V1, STATE_V2
from vimtg.data.database import Database
from vimtg.data.snapshot_repository import SnapshotRepository
from vimtg.services.vcs_service import VersionControlService


@pytest.fixture
def vcs(db_factory: Callable[..., Database]) -> VersionControlService:
    return VersionControlService(SnapshotRepository(db_factory()), DECK_PATH)


@pytest.fixture
def vcs_with_history(vcs: VersionControlService) -> VersionControlService:
    vcs.commit(STATE_V1, "initial build")
    vcs.commit(STATE_V2, "add swiftspear")
    return vcs

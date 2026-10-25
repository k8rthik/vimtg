"""Persisting Scryfall oracle tags (vimtg.data.tag_repository)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from vimtg.data.database import Database
from vimtg.data.tag_repository import TagRepository
from vimtg.domain.oracle_tags import OracleTag

FIXTURE = Path(__file__).parent.parent / "fixtures" / "scryfall_oracle_tags.jsonl"


@pytest.fixture
def tags() -> list[OracleTag]:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    return [OracleTag.from_scryfall(json.loads(line)) for line in lines if line.strip()]


@pytest.fixture
def repo(db_factory: Callable[..., Database]) -> TagRepository:
    return TagRepository(db_factory())


class TestEmpty:
    def test_fresh_database_has_no_tags(self, repo: TagRepository) -> None:
        assert not repo.has_tags()
        assert repo.count() == 0
        assert repo.get_last_sync() is None


class TestReplaceAll:
    def test_loads_every_expanded_row_and_stamps_the_sync(
        self, repo: TagRepository, tags: list[OracleTag]
    ) -> None:
        assert repo.replace_all(tags, synced_at="2026-10-25T00:00:00+00:00") == 10
        assert repo.has_tags()
        assert repo.count() == 16  # see tests/domain/test_oracle_tags.py
        assert repo.get_last_sync() == "2026-10-25T00:00:00+00:00"

    def test_second_load_replaces_the_first(
        self, repo: TagRepository, tags: list[OracleTag]
    ) -> None:
        repo.replace_all(tags, synced_at="2026-10-25T00:00:00+00:00")
        only_rhystic = [t for t in tags if t.slug == "rhystic"]
        assert repo.replace_all(only_rhystic, synced_at="2026-10-26T00:00:00+00:00") == 1
        assert repo.count() == 1
        assert repo.get_last_sync() == "2026-10-26T00:00:00+00:00"

    def test_empty_load_is_refused(self, repo: TagRepository, tags: list[OracleTag]) -> None:
        repo.replace_all(tags, synced_at="2026-10-25T00:00:00+00:00")
        with pytest.raises(ValueError, match="no oracle tags"):
            repo.replace_all([], synced_at="2026-10-26T00:00:00+00:00")
        assert repo.count() == 16

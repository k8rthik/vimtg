"""The oracle-tag fixture, loaded next to a card repository's cards."""

from __future__ import annotations

import json
from pathlib import Path

from vimtg.data.card_repository import CardRepository
from vimtg.data.tag_repository import TagRepository
from vimtg.domain.oracle_tags import OracleTag

FIXTURE_TAGS = Path(__file__).parent / "fixtures" / "scryfall_oracle_tags.jsonl"


def fixture_tags() -> list[OracleTag]:
    lines = FIXTURE_TAGS.read_text(encoding="utf-8").splitlines()
    return [OracleTag.from_scryfall(json.loads(line)) for line in lines if line.strip()]


def load_fixture_tags(repo: CardRepository) -> None:
    """Sol Ring under ramp, the burn spells under removal (see the fixture)."""
    TagRepository(repo.database).replace_all(
        fixture_tags(), synced_at="2026-10-25T00:00:00+00:00"
    )

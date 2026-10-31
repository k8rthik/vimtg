"""Scryfall oracle tags: parsing a tag record and expanding the hierarchy."""

from __future__ import annotations

import json
from pathlib import Path

from vimtg.domain.oracle_tags import (
    OracleTag,
    alias_rows,
    card_tag_rows,
    implied_slugs,
    normalize_tag,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "scryfall_oracle_tags.jsonl"

SOL_RING = "11110011-0a0b-4c0d-8e0f-000000000011"
BOLT = "11110015-0a0b-4c0d-8e0f-000000000015"
RHYSTIC = "11110012-0a0b-4c0d-8e0f-000000000012"


def _fixture_tags() -> list[OracleTag]:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    return [OracleTag.from_scryfall(json.loads(line)) for line in lines if line.strip()]


class TestFromScryfall:
    def test_reads_the_fields_search_needs(self) -> None:
        tag = next(t for t in _fixture_tags() if t.slug == "mana-rock")
        assert tag.id == "523a4f29-25ee-483c-8123-a8e62b62af5a"
        assert tag.parent_ids == ("5f1260dd-e1dc-435a-a9ff-ce7172b7a5cd",)
        assert "manarock" in tag.aliases
        assert tag.oracle_ids == (SOL_RING,)

    def test_missing_lists_are_empty(self) -> None:
        tag = OracleTag.from_scryfall({"id": "x", "slug": "lonely"})
        assert tag == OracleTag(id="x", slug="lonely")


class TestNormalizeTag:
    def test_lowercases_and_hyphenates_spaces(self) -> None:
        assert normalize_tag("Mana Ramp") == "mana-ramp"
        assert normalize_tag("  spot   removal ") == "spot-removal"
        assert normalize_tag("tutor-creature") == "tutor-creature"


class TestImpliedSlugs:
    def test_a_tag_implies_itself_and_every_ancestor(self) -> None:
        tags = _fixture_tags()
        by_slug = {t.slug: t for t in tags}
        implied = implied_slugs(tags)
        assert implied[by_slug["mana-rock"].id] == {"mana-rock", "mana-producer", "ramp"}
        assert implied[by_slug["ramp"].id] == {"ramp"}

    def test_multiple_parents_are_all_implied(self) -> None:
        tags = _fixture_tags()
        by_slug = {t.slug: t for t in tags}
        assert implied_slugs(tags)[by_slug["removal-burn"].id] == {
            "removal-burn", "burn", "removal",
        }

    def test_unknown_parent_is_ignored(self) -> None:
        # rhystic's parent (tax) is not in the fixture
        tags = _fixture_tags()
        by_slug = {t.slug: t for t in tags}
        assert implied_slugs(tags)[by_slug["rhystic"].id] == {"rhystic"}

    def test_a_cycle_terminates(self) -> None:
        a = OracleTag(id="a", slug="a", parent_ids=("b",))
        b = OracleTag(id="b", slug="b", parent_ids=("a",))
        assert implied_slugs([a, b]) == {"a": {"a", "b"}, "b": {"a", "b"}}


class TestRows:
    def test_card_rows_cover_ancestors_once(self) -> None:
        rows = set(card_tag_rows(_fixture_tags()))
        assert {s for o, s in rows if o == SOL_RING} == {"mana-rock", "mana-producer", "ramp"}
        # Bolt is tagged removal-burn and spot-removal: removal appears once
        assert sorted(s for o, s in rows if o == BOLT) == [
            "burn", "removal", "removal-burn", "spot-removal",
        ]
        assert {s for o, s in rows if o == RHYSTIC} == {"rhystic", "draw", "card-advantage"}
        assert len(rows) == 16

    def test_card_rows_are_not_repeated(self) -> None:
        rows = list(card_tag_rows(_fixture_tags()))
        assert len(rows) == len(set(rows))

    def test_alias_rows_point_at_the_slug_in_slug_form(self) -> None:
        aliases = dict(alias_rows(_fixture_tags()))
        assert aliases["mana-ramp"] == "ramp"
        assert aliases["acceleration"] == "ramp"
        assert aliases["manarock"] == "mana-rock"

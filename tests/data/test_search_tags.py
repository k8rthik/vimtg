"""``otag:`` searches against the loaded tag tables: which cards match."""

from __future__ import annotations

import pytest

from tests.tag_support import load_fixture_tags
from vimtg.data.card_repository import CardRepository
from vimtg.services.search_service import SearchService


@pytest.fixture
def tagged(real_shape_repo: CardRepository) -> SearchService:
    load_fixture_tags(real_shape_repo)
    return SearchService(card_repo=real_shape_repo)


@pytest.fixture
def untagged(real_shape_repo: CardRepository) -> SearchService:
    return SearchService(card_repo=real_shape_repo)


def _names(service: SearchService, query: str) -> set[str]:
    return {card.name for card in service.search(query, limit=50)}


class TestMatching:
    def test_ancestor_tag_finds_a_card_tagged_with_a_leaf(self, tagged: SearchService) -> None:
        # Sol Ring is tagged mana-rock, under mana-producer, under ramp
        assert _names(tagged, "otag:ramp") == {"Sol Ring"}
        assert _names(tagged, "otag:mana-producer") == {"Sol Ring"}
        assert _names(tagged, "otag:mana-rock") == {"Sol Ring"}

    def test_alias_resolves_to_its_tag(self, tagged: SearchService) -> None:
        assert _names(tagged, "otag:acceleration") == {"Sol Ring"}
        assert _names(tagged, 'otag:"mana ramp"') == {"Sol Ring"}
        assert _names(tagged, "otag:manarock") == {"Sol Ring"}

    def test_multiple_parents(self, tagged: SearchService) -> None:
        burn = {"Lightning Bolt", "Fire // Ice", "Bonecrusher Giant // Stomp"}
        assert _names(tagged, "otag:removal") == burn
        assert _names(tagged, "otag:burn") == burn

    def test_combines_with_other_terms(self, tagged: SearchService) -> None:
        assert _names(tagged, "otag:removal t:instant -t:creature") == {
            "Lightning Bolt", "Fire // Ice",
        }
        assert _names(tagged, "-otag:removal t:instant") == {
            "Lim-Dûl's Vault", "Valakut Awakening // Valakut Stoneforge",
        }
        assert _names(tagged, "otag:ramp or otag:rhystic") == {"Sol Ring", "Rhystic Study"}

    def test_unknown_tag_matches_nothing(self, tagged: SearchService) -> None:
        assert _names(tagged, "otag:no-such-tag") == set()

    def test_order_still_applies(self, tagged: SearchService) -> None:
        names = [c.name for c in tagged.search("otag:removal order:cmc direction:desc")]
        # Fire // Ice is mana value 4 (both halves), Stomp's card 3, Bolt 1
        assert names == ["Fire // Ice", "Bonecrusher Giant // Stomp", "Lightning Bolt"]


class TestUnsyncedTags:
    def test_no_tags_means_no_matches_and_a_reason(self, untagged: SearchService) -> None:
        assert _names(untagged, "otag:ramp") == set()
        assert untagged.tags_unsynced("otag:ramp")
        assert untagged.tags_unsynced("t:artifact -otag:ramp")

    def test_queries_without_tags_never_complain(self, untagged: SearchService) -> None:
        assert not untagged.tags_unsynced("t:artifact")
        assert not untagged.tags_unsynced("")

    def test_synced_tags_do_not_complain(self, tagged: SearchService) -> None:
        assert not tagged.tags_unsynced("otag:no-such-tag")

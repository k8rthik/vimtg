"""Tests for SearchService with Scryfall syntax parsing."""

import json
from pathlib import Path

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card, Color, Rarity
from vimtg.services.search_service import SearchService

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def card_repo(tmp_db: Path) -> CardRepository:
    db = Database(tmp_db)
    db.initialize()
    repo = CardRepository(db)
    with open(FIXTURES_DIR / "scryfall_sample.json") as f:
        cards_data = json.load(f)
    cards = [Card.from_scryfall(d) for d in cards_data]
    repo.bulk_insert(cards)
    return repo


@pytest.fixture
def search_svc(card_repo: CardRepository) -> SearchService:
    return SearchService(card_repo=card_repo)


class TestFuzzySearch:
    def test_bolt(self, search_svc: SearchService) -> None:
        results = search_svc.fuzzy_search("bolt")
        names = [c.name for c in results]
        assert "Lightning Bolt" in names

    def test_empty_returns_nothing(self, search_svc: SearchService) -> None:
        results = search_svc.fuzzy_search("")
        assert results == []


class TestParseQuery:
    def test_type_creature(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("t:creature")
        assert sq.type_contains == "creature"
        assert sq.text == ""

    def test_type_long_prefix(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("type:instant")
        assert sq.type_contains == "instant"

    def test_color_red(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("c:r")
        assert sq.colors_include == (Color.RED,)

    def test_color_multichar(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("c:rg")
        assert Color.RED in sq.colors_include
        assert Color.GREEN in sq.colors_include

    def test_color_long_prefix(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("color:wu")
        assert Color.WHITE in sq.colors_include
        assert Color.BLUE in sq.colors_include

    def test_cmc_lte(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("cmc<=3")
        assert sq.cmc_lte == 3.0
        assert sq.cmc_eq is None
        assert sq.cmc_gte is None

    def test_cmc_gte(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("cmc>=5")
        assert sq.cmc_gte == 5.0

    def test_cmc_eq(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("cmc=2")
        assert sq.cmc_eq == 2.0

    def test_oracle_quoted(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query('o:"draw a card"')
        assert sq.oracle_contains == "draw a card"

    def test_oracle_long_prefix(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query('oracle:"deals 3 damage"')
        assert sq.oracle_contains == "deals 3 damage"

    def test_set_code(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("set:mh2")
        assert sq.set_code == "mh2"

    def test_rarity_mythic(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("r:mythic")
        assert sq.rarity == Rarity.MYTHIC

    def test_rarity_long_prefix(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("rarity:rare")
        assert sq.rarity == Rarity.RARE

    def test_rarity_invalid(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("r:legendary")
        assert sq.rarity is None

    def test_plain_text(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("lightning bolt")
        assert sq.text == "lightning bolt"
        assert sq.type_contains is None
        assert sq.colors_include == ()

    def test_combined(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("t:creature c:r cmc<=3")
        assert sq.type_contains == "creature"
        assert sq.colors_include == (Color.RED,)
        assert sq.cmc_lte == 3.0

    def test_empty_query(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("")
        assert sq.is_empty()

    def test_cmc_invalid(self, search_svc: SearchService) -> None:
        sq = search_svc.parse_query("cmc<=abc")
        assert sq.cmc_lte is None


class TestAdvancedSearch:
    def test_type_filter(self, search_svc: SearchService) -> None:
        results = search_svc.advanced_search("t:creature")
        names = [c.name for c in results]
        assert "Goblin Guide" in names
        assert "Lightning Bolt" not in names

    def test_set_filter(self, search_svc: SearchService) -> None:
        results = search_svc.advanced_search("set:zen")
        names = [c.name for c in results]
        assert "Goblin Guide" in names
        assert len(names) == 1

    def test_rarity_filter(self, search_svc: SearchService) -> None:
        results = search_svc.advanced_search("r:rare")
        names = [c.name for c in results]
        assert "Goblin Guide" in names
        assert "Lightning Bolt" not in names

    def test_cmc_filter(self, search_svc: SearchService) -> None:
        results = search_svc.advanced_search("cmc<=1")
        for card in results:
            assert card.cmc <= 1.0

    def test_oracle_filter(self, search_svc: SearchService) -> None:
        results = search_svc.advanced_search("o:\"deals 3 damage\"")
        names = [c.name for c in results]
        assert "Lightning Bolt" in names

    def test_empty_returns_nothing(self, search_svc: SearchService) -> None:
        results = search_svc.advanced_search("")
        assert results == []

    def test_text_only_uses_fts(self, search_svc: SearchService) -> None:
        results = search_svc.advanced_search("bolt")
        names = [c.name for c in results]
        assert "Lightning Bolt" in names


class TestAutocomplete:
    def test_gob_prefix(self, search_svc: SearchService) -> None:
        results = search_svc.autocomplete("Gob")
        assert "Goblin Guide" in results

    def test_empty_prefix(self, search_svc: SearchService) -> None:
        results = search_svc.autocomplete("")
        assert results == []

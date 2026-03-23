import json
from pathlib import Path

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card

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
def empty_repo(tmp_db: Path) -> CardRepository:
    db = Database(tmp_db)
    db.initialize()
    return CardRepository(db)


@pytest.fixture
def sample_cards() -> list[Card]:
    with open(FIXTURES_DIR / "scryfall_sample.json") as f:
        cards_data = json.load(f)
    return [Card.from_scryfall(d) for d in cards_data]


class TestBulkInsert:
    def test_returns_count(self, empty_repo: CardRepository, sample_cards: list[Card]) -> None:
        count = empty_repo.bulk_insert(sample_cards)
        assert count == 10

    def test_idempotent(self, empty_repo: CardRepository, sample_cards: list[Card]) -> None:
        empty_repo.bulk_insert(sample_cards)
        empty_repo.bulk_insert(sample_cards)
        assert empty_repo.count() == 10

    def test_empty_list(self, empty_repo: CardRepository) -> None:
        count = empty_repo.bulk_insert([])
        assert count == 0


class TestSearch:
    def test_exact_name(self, card_repo: CardRepository) -> None:
        results = card_repo.search("Lightning Bolt")
        assert len(results) > 0
        assert results[0].name == "Lightning Bolt"

    def test_prefix(self, card_repo: CardRepository) -> None:
        results = card_repo.search("light")
        names = [c.name for c in results]
        assert "Lightning Bolt" in names

    def test_multiword(self, card_repo: CardRepository) -> None:
        results = card_repo.search("goblin guide")
        assert len(results) > 0
        assert results[0].name == "Goblin Guide"

    def test_limit(self, card_repo: CardRepository) -> None:
        results = card_repo.search("creature", limit=2)
        assert len(results) <= 2

    def test_empty_query(self, card_repo: CardRepository) -> None:
        results = card_repo.search("")
        assert results == []

    def test_whitespace_only(self, card_repo: CardRepository) -> None:
        results = card_repo.search("   ")
        assert results == []


class TestGetByName:
    def test_exact_match(self, card_repo: CardRepository) -> None:
        card = card_repo.get_by_name("Lightning Bolt")
        assert card is not None
        assert card.name == "Lightning Bolt"

    def test_case_insensitive(self, card_repo: CardRepository) -> None:
        card = card_repo.get_by_name("lightning bolt")
        assert card is not None
        assert card.name == "Lightning Bolt"

    def test_not_found(self, card_repo: CardRepository) -> None:
        card = card_repo.get_by_name("Nonexistent Card")
        assert card is None


class TestGetByNames:
    def test_batch_lookup(self, card_repo: CardRepository) -> None:
        names = ["Lightning Bolt", "Goblin Guide", "Mountain"]
        result = card_repo.get_by_names(names)
        assert len(result) == 3
        assert "Lightning Bolt" in result
        assert "Goblin Guide" in result
        assert "Mountain" in result

    def test_partial_match(self, card_repo: CardRepository) -> None:
        names = ["Lightning Bolt", "Nonexistent Card"]
        result = card_repo.get_by_names(names)
        assert len(result) == 1
        assert "Lightning Bolt" in result
        assert "Nonexistent Card" not in result

    def test_empty_input(self, card_repo: CardRepository) -> None:
        result = card_repo.get_by_names([])
        assert result == {}


class TestAutocomplete:
    def test_prefix_match(self, card_repo: CardRepository) -> None:
        results = card_repo.autocomplete("Gob")
        assert "Goblin Guide" in results

    def test_limit(self, card_repo: CardRepository) -> None:
        results = card_repo.autocomplete("", limit=3)
        assert len(results) <= 3

    def test_empty_prefix(self, card_repo: CardRepository) -> None:
        results = card_repo.autocomplete("")
        assert results == []


class TestCount:
    def test_count_after_insert(self, card_repo: CardRepository) -> None:
        assert card_repo.count() == 10

    def test_count_empty(self, empty_repo: CardRepository) -> None:
        assert empty_repo.count() == 0


class TestSyncMetadata:
    def test_set_and_get(self, card_repo: CardRepository) -> None:
        card_repo.set_last_sync("2025-01-15T10:30:00Z")
        result = card_repo.get_last_sync()
        assert result == "2025-01-15T10:30:00Z"

    def test_get_when_unset(self, empty_repo: CardRepository) -> None:
        result = empty_repo.get_last_sync()
        assert result is None

    def test_overwrite(self, card_repo: CardRepository) -> None:
        card_repo.set_last_sync("2025-01-01T00:00:00Z")
        card_repo.set_last_sync("2025-02-01T00:00:00Z")
        result = card_repo.get_last_sync()
        assert result == "2025-02-01T00:00:00Z"


class TestRowToCardRoundTrip:
    def test_preserves_all_fields(self, card_repo: CardRepository) -> None:
        """Verify no data loss in Card -> row -> Card serialization roundtrip."""
        with open(FIXTURES_DIR / "scryfall_sample.json") as f:
            cards_data = json.load(f)
        original = Card.from_scryfall(cards_data[0])  # Goblin Guide

        retrieved = card_repo.get_by_name("Goblin Guide")
        assert retrieved is not None

        assert retrieved.scryfall_id == original.scryfall_id
        assert retrieved.name == original.name
        assert retrieved.mana_cost == original.mana_cost
        assert retrieved.cmc == original.cmc
        assert retrieved.type_line == original.type_line
        assert retrieved.oracle_text == original.oracle_text
        assert retrieved.colors == original.colors
        assert retrieved.color_identity == original.color_identity
        assert retrieved.power == original.power
        assert retrieved.toughness == original.toughness
        assert retrieved.set_code == original.set_code
        assert retrieved.rarity == original.rarity
        assert retrieved.price_usd == original.price_usd
        assert retrieved.legalities == original.legalities
        assert retrieved.image_uri == original.image_uri
        assert retrieved.layout == original.layout
        assert retrieved.keywords == original.keywords

    def test_preserves_null_price(self, card_repo: CardRepository) -> None:
        """Mountain has null price_usd."""
        card = card_repo.get_by_name("Mountain")
        assert card is not None
        assert card.price_usd is None

    def test_preserves_empty_colors(self, card_repo: CardRepository) -> None:
        """Mountain has no colors."""
        card = card_repo.get_by_name("Mountain")
        assert card is not None
        assert card.colors == ()

    def test_preserves_transform_layout(self, card_repo: CardRepository) -> None:
        """Delver of Secrets is a transform card."""
        card = card_repo.get_by_name("Delver of Secrets // Insectile Aberration")
        assert card is not None
        assert card.layout == "transform"
        assert card.keywords == ("Transform",)

import json
from pathlib import Path

import pytest

from vimtg.domain.card import Card, Color, Rarity


@pytest.fixture
def scryfall_cards() -> list[dict]:
    path = Path(__file__).parent.parent / "fixtures" / "scryfall_sample.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def goblin_guide(scryfall_cards: list[dict]) -> dict:
    return next(c for c in scryfall_cards if c["name"] == "Goblin Guide")


@pytest.fixture
def lightning_bolt(scryfall_cards: list[dict]) -> dict:
    return next(c for c in scryfall_cards if c["name"] == "Lightning Bolt")


@pytest.fixture
def lava_spike(scryfall_cards: list[dict]) -> dict:
    return next(c for c in scryfall_cards if c["name"] == "Lava Spike")


@pytest.fixture
def eidolon(scryfall_cards: list[dict]) -> dict:
    return next(c for c in scryfall_cards if c["name"] == "Eidolon of the Great Revel")


@pytest.fixture
def sacred_foundry(scryfall_cards: list[dict]) -> dict:
    return next(c for c in scryfall_cards if c["name"] == "Sacred Foundry")


@pytest.fixture
def delver(scryfall_cards: list[dict]) -> dict:
    return next(c for c in scryfall_cards if "Delver" in c["name"])


@pytest.fixture
def fire_ice(scryfall_cards: list[dict]) -> dict:
    return next(c for c in scryfall_cards if c["name"] == "Fire // Ice")


@pytest.fixture
def bonecrusher(scryfall_cards: list[dict]) -> dict:
    return next(c for c in scryfall_cards if "Bonecrusher" in c["name"])


@pytest.fixture
def mountain(scryfall_cards: list[dict]) -> dict:
    return next(c for c in scryfall_cards if c["name"] == "Mountain")


class TestFromScryfallNormal:
    def test_normal_creature(self, goblin_guide: dict) -> None:
        card = Card.from_scryfall(goblin_guide)
        assert card.name == "Goblin Guide"
        assert card.mana_cost == "{R}"
        assert card.cmc == 1.0
        assert card.type_line == "Creature \u2014 Goblin Scout"
        assert "Haste" in card.oracle_text
        assert card.colors == (Color.RED,)
        assert card.color_identity == (Color.RED,)
        assert card.power == "2"
        assert card.toughness == "2"
        assert card.set_code == "zen"
        assert card.rarity == Rarity.RARE
        assert card.price_usd == 3.50
        assert card.layout == "normal"

    def test_instant(self, lightning_bolt: dict) -> None:
        card = Card.from_scryfall(lightning_bolt)
        assert card.name == "Lightning Bolt"
        assert card.mana_cost == "{R}"
        assert card.type_line == "Instant"
        assert "3 damage" in card.oracle_text
        assert card.power is None
        assert card.toughness is None
        assert card.rarity == Rarity.UNCOMMON

    def test_sorcery(self, lava_spike: dict) -> None:
        card = Card.from_scryfall(lava_spike)
        assert card.name == "Lava Spike"
        assert card.type_line == "Sorcery \u2014 Arcane"
        assert "3 damage" in card.oracle_text

    def test_enchantment_creature(self, eidolon: dict) -> None:
        card = Card.from_scryfall(eidolon)
        assert card.name == "Eidolon of the Great Revel"
        assert card.mana_cost == "{R}{R}"
        assert card.cmc == 2.0
        assert card.is_creature
        assert card.power == "2"
        assert card.toughness == "2"

    def test_land(self, sacred_foundry: dict) -> None:
        card = Card.from_scryfall(sacred_foundry)
        assert card.name == "Sacred Foundry"
        assert card.mana_cost == ""
        assert card.cmc == 0.0
        assert card.colors == ()
        assert set(card.color_identity) == {Color.RED, Color.WHITE}
        assert card.is_land


class TestFromScryfallDFC:
    def test_transform_card(self, delver: dict) -> None:
        card = Card.from_scryfall(delver)
        assert card.name == "Delver of Secrets // Insectile Aberration"
        assert card.mana_cost == "{U}"
        assert card.oracle_text == (
            "At the beginning of your upkeep, look at the top card of your library. "
            "You may reveal that card. If an instant or sorcery card is revealed this way, "
            "transform Delver of Secrets."
        )
        assert card.power == "1"
        assert card.toughness == "1"
        assert card.colors == (Color.BLUE,)
        assert card.layout == "transform"

    def test_split_card(self, fire_ice: dict) -> None:
        card = Card.from_scryfall(fire_ice)
        assert card.name == "Fire // Ice"
        assert "Fire deals 2 damage" in card.oracle_text
        assert "Tap target permanent" in card.oracle_text
        assert "\n//\n" in card.oracle_text
        assert card.layout == "split"

    def test_adventure_card(self, bonecrusher: dict) -> None:
        card = Card.from_scryfall(bonecrusher)
        assert card.name == "Bonecrusher Giant // Stomp"
        assert card.mana_cost == "{2}{R}"
        assert card.power == "4"
        assert card.toughness == "3"
        assert "Bonecrusher Giant becomes the target" in card.oracle_text
        assert "Damage can't be prevented" in card.oracle_text
        assert card.layout == "adventure"


class TestFromScryfallEdgeCases:
    def test_missing_price(self, mountain: dict) -> None:
        card = Card.from_scryfall(mountain)
        assert card.price_usd is None

    def test_missing_image_fallback(self, delver: dict) -> None:
        card = Card.from_scryfall(delver)
        assert card.image_uri is not None
        assert "delver-front" in card.image_uri

    def test_keywords(self, goblin_guide: dict) -> None:
        card = Card.from_scryfall(goblin_guide)
        assert card.keywords == ("Haste",)

    def test_empty_keywords(self, lightning_bolt: dict) -> None:
        card = Card.from_scryfall(lightning_bolt)
        assert card.keywords == ()

    def test_unknown_rarity_maps_to_special(self, goblin_guide: dict) -> None:
        data = {**goblin_guide, "rarity": "timeshifted"}
        card = Card.from_scryfall(data)
        assert card.rarity == Rarity.SPECIAL

    def test_all_fixture_cards_parse(self, scryfall_cards: list[dict]) -> None:
        for data in scryfall_cards:
            card = Card.from_scryfall(data)
            assert card.name
            assert card.scryfall_id


class TestCardProperties:
    def test_is_creature_true(self, goblin_guide: dict) -> None:
        card = Card.from_scryfall(goblin_guide)
        assert card.is_creature is True

    def test_is_creature_false(self, lightning_bolt: dict) -> None:
        card = Card.from_scryfall(lightning_bolt)
        assert card.is_creature is False

    def test_is_land_true(self, sacred_foundry: dict) -> None:
        card = Card.from_scryfall(sacred_foundry)
        assert card.is_land is True

    def test_is_land_false(self, goblin_guide: dict) -> None:
        card = Card.from_scryfall(goblin_guide)
        assert card.is_land is False

    def test_is_instant_or_sorcery_instant(self, lightning_bolt: dict) -> None:
        card = Card.from_scryfall(lightning_bolt)
        assert card.is_instant_or_sorcery is True

    def test_is_instant_or_sorcery_sorcery(self, lava_spike: dict) -> None:
        card = Card.from_scryfall(lava_spike)
        assert card.is_instant_or_sorcery is True

    def test_is_instant_or_sorcery_false(self, goblin_guide: dict) -> None:
        card = Card.from_scryfall(goblin_guide)
        assert card.is_instant_or_sorcery is False


class TestCardImmutability:
    def test_card_is_frozen(self, goblin_guide: dict) -> None:
        card = Card.from_scryfall(goblin_guide)
        with pytest.raises(AttributeError):
            card.name = "Modified Name"  # type: ignore[misc]

    def test_card_is_frozen_prices(self, goblin_guide: dict) -> None:
        card = Card.from_scryfall(goblin_guide)
        with pytest.raises(AttributeError):
            card.prices = None  # type: ignore[misc]

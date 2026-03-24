"""Tests for deck analytics — mana curve, color distribution, stats."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.domain.analytics import (
    compute_stats,
    count_mana_pips,
)
from vimtg.domain.card import Card, Color, Prices
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection

# --- Fixtures ---


@pytest.fixture
def scryfall_cards() -> list[dict]:
    path = Path(__file__).parent.parent / "fixtures" / "scryfall_sample.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def card_map(scryfall_cards: list[dict]) -> dict[str, Card]:
    """All sample cards keyed by name."""
    return {c["name"]: Card.from_scryfall(c) for c in scryfall_cards}


def _entry(qty: int, name: str, section: DeckSection = DeckSection.MAIN) -> DeckEntry:
    return DeckEntry(quantity=qty, card_name=name, section=section)


def _make_deck(entries: tuple[DeckEntry, ...]) -> Deck:
    return Deck(metadata=DeckMetadata(), entries=entries, comments=())


# --- count_mana_pips ---


class TestCountManaPips:
    def test_single_color(self) -> None:
        result = count_mana_pips("{2}{R}{R}")
        assert result == {Color.RED: 2}

    def test_multicolor(self) -> None:
        result = count_mana_pips("{W}{U}{B}")
        assert result == {Color.WHITE: 1, Color.BLUE: 1, Color.BLACK: 1}

    def test_empty_cost(self) -> None:
        result = count_mana_pips("")
        assert result == {}

    def test_colorless_only(self) -> None:
        result = count_mana_pips("{3}")
        assert result == {}

    def test_hybrid_ignored(self) -> None:
        """Hybrid symbols like {R/G} are not single-letter, so ignored."""
        result = count_mana_pips("{R/G}{R}")
        assert result == {Color.RED: 1}


# --- ManaCurve ---


class TestManaCurve:
    def test_basic_curve(self, card_map: dict[str, Card]) -> None:
        """4 Goblin Guide (cmc=1) + 4 Eidolon (cmc=2) => bucket 1=4, 2=4."""
        deck = _make_deck((
            _entry(4, "Goblin Guide"),
            _entry(4, "Eidolon of the Great Revel"),
        ))
        stats = compute_stats(deck, card_map)
        curve = stats.mana_curve
        assert curve.buckets[1] == 4
        assert curve.buckets[2] == 4
        assert curve.total() == 8

    def test_empty_curve(self) -> None:
        deck = _make_deck(())
        stats = compute_stats(deck, {})
        curve = stats.mana_curve
        assert curve.max_count() == 0
        assert curve.total() == 0

    def test_seven_plus_bucket(self, card_map: dict[str, Card]) -> None:
        """Cards with cmc >= 7 go into bucket 7."""
        high_cmc_card = Card(
            scryfall_id="high-cmc",
            name="Big Spell",
            mana_cost="{5}{R}{R}",
            cmc=9.0,
            type_line="Sorcery",
            oracle_text="",
            colors=(Color.RED,),
            color_identity=(Color.RED,),
            power=None,
            toughness=None,
            set_code="tst",
            rarity=card_map["Goblin Guide"].rarity,
            prices=Prices(),
            legalities={},
            image_uri=None,
            layout="normal",
            keywords=(),
        )
        resolved = {**card_map, "Big Spell": high_cmc_card}
        deck = _make_deck((_entry(2, "Big Spell"),))
        stats = compute_stats(deck, resolved)
        assert stats.mana_curve.buckets[7] == 2


# --- ColorDistribution ---


class TestColorDistribution:
    def test_mono_red_pips(self, card_map: dict[str, Card]) -> None:
        """4x Eidolon ({R}{R}) => 8 red pips."""
        deck = _make_deck((_entry(4, "Eidolon of the Great Revel"),))
        stats = compute_stats(deck, card_map)
        dist = stats.color_distribution
        assert dist.pips[Color.RED] == 8

    def test_card_colors(self, card_map: dict[str, Card]) -> None:
        deck = _make_deck((
            _entry(4, "Lightning Bolt"),
            _entry(2, "Rest in Peace", DeckSection.MAIN),
        ))
        stats = compute_stats(deck, card_map)
        dist = stats.color_distribution
        assert dist.cards[Color.RED] == 4
        assert dist.cards[Color.WHITE] == 2

    def test_colorless_count(self, card_map: dict[str, Card]) -> None:
        """Lands and colorless cards counted."""
        deck = _make_deck((_entry(4, "Mountain"),))
        stats = compute_stats(deck, card_map)
        assert stats.color_distribution.colorless_count == 4


# --- TypeBreakdown ---


class TestTypeBreakdown:
    def test_creatures_vs_instants(self, card_map: dict[str, Card]) -> None:
        deck = _make_deck((
            _entry(4, "Goblin Guide"),
            _entry(4, "Lightning Bolt"),
        ))
        stats = compute_stats(deck, card_map)
        types = stats.type_breakdown
        assert types.counts["Creature"] == 4
        assert types.counts["Instant"] == 4
        assert types.total_nonland() == 8

    def test_land_excluded_from_nonland_total(self, card_map: dict[str, Card]) -> None:
        deck = _make_deck((
            _entry(4, "Goblin Guide"),
            _entry(4, "Mountain"),
        ))
        stats = compute_stats(deck, card_map)
        assert stats.type_breakdown.total_nonland() == 4

    def test_enchantment_creature_classified(self, card_map: dict[str, Card]) -> None:
        """Eidolon is 'Enchantment Creature' — first match is Creature."""
        deck = _make_deck((_entry(2, "Eidolon of the Great Revel"),))
        stats = compute_stats(deck, card_map)
        assert stats.type_breakdown.counts.get("Creature") == 2


# --- compute_stats ---


class TestComputeStats:
    def test_total_cards(self, card_map: dict[str, Card]) -> None:
        deck = _make_deck((
            _entry(4, "Goblin Guide"),
            _entry(4, "Lightning Bolt"),
            _entry(2, "Rest in Peace", DeckSection.SIDEBOARD),
        ))
        stats = compute_stats(deck, card_map)
        assert stats.total_cards == 10
        assert stats.mainboard_count == 8
        assert stats.sideboard_count == 2

    def test_avg_cmc_nonland_only(self, card_map: dict[str, Card]) -> None:
        """avg cmc computed from nonland only: 4x cmc=1, 4x cmc=2 => 1.5."""
        deck = _make_deck((
            _entry(4, "Goblin Guide"),
            _entry(4, "Eidolon of the Great Revel"),
            _entry(4, "Mountain"),
        ))
        stats = compute_stats(deck, card_map)
        assert stats.average_cmc == 1.5

    def test_median_cmc(self, card_map: dict[str, Card]) -> None:
        """4x cmc=1, 4x cmc=2 => sorted = [1,1,1,1,2,2,2,2], median at index 4 = 2."""
        deck = _make_deck((
            _entry(4, "Goblin Guide"),
            _entry(4, "Eidolon of the Great Revel"),
        ))
        stats = compute_stats(deck, card_map)
        assert stats.median_cmc == 2.0

    def test_price_sum(self, card_map: dict[str, Card]) -> None:
        """4x Goblin Guide ($3.50) + 4x Lightning Bolt ($1.50) = $20."""
        deck = _make_deck((
            _entry(4, "Goblin Guide"),
            _entry(4, "Lightning Bolt"),
        ))
        stats = compute_stats(deck, card_map)
        assert stats.total_price_usd == 20.0

    def test_price_none_when_no_prices(self) -> None:
        """All cards without prices => total_price_usd is None."""
        card_no_price = Card(
            scryfall_id="np",
            name="No Price Card",
            mana_cost="{R}",
            cmc=1.0,
            type_line="Instant",
            oracle_text="",
            colors=(Color.RED,),
            color_identity=(Color.RED,),
            power=None,
            toughness=None,
            set_code="tst",
            rarity=None,  # type: ignore[arg-type]
            prices=Prices(),
            legalities={},
            image_uri=None,
            layout="normal",
            keywords=(),
        )
        deck = _make_deck((_entry(4, "No Price Card"),))
        stats = compute_stats(deck, {"No Price Card": card_no_price})
        assert stats.total_price_usd is None

    def test_land_count(self, card_map: dict[str, Card]) -> None:
        deck = _make_deck((
            _entry(4, "Mountain"),
            _entry(4, "Sacred Foundry"),
            _entry(4, "Lightning Bolt"),
        ))
        stats = compute_stats(deck, card_map)
        assert stats.land_count == 8
        assert stats.nonland_count == 4

    def test_recommended_lands_reasonable(self, card_map: dict[str, Card]) -> None:
        deck = _make_deck((
            _entry(4, "Goblin Guide"),
            _entry(4, "Lightning Bolt"),
            _entry(4, "Lava Spike"),
            _entry(4, "Eidolon of the Great Revel"),
            _entry(4, "Mountain"),
        ))
        stats = compute_stats(deck, card_map)
        assert 20 <= stats.recommended_lands <= 28

    def test_empty_deck(self) -> None:
        deck = _make_deck(())
        stats = compute_stats(deck, {})
        assert stats.total_cards == 0
        assert stats.mainboard_count == 0
        assert stats.sideboard_count == 0
        assert stats.average_cmc == 0.0
        assert stats.median_cmc == 0.0
        assert stats.land_count == 0
        assert stats.nonland_count == 0
        assert stats.total_price_usd is None
        assert stats.recommended_lands == 24

    def test_unresolved_cards_graceful(self) -> None:
        """Cards not in resolved_cards are silently skipped."""
        deck = _make_deck((
            _entry(4, "Unknown Card"),
            _entry(4, "Another Missing"),
        ))
        stats = compute_stats(deck, {})
        assert stats.mainboard_count == 8
        assert stats.nonland_count == 0
        assert stats.land_count == 0
        assert stats.average_cmc == 0.0

    def test_unique_cards_counts_across_sections(self, card_map: dict[str, Card]) -> None:
        deck = _make_deck((
            _entry(4, "Lightning Bolt"),
            _entry(2, "Lightning Bolt", DeckSection.SIDEBOARD),
            _entry(4, "Goblin Guide"),
        ))
        stats = compute_stats(deck, card_map)
        assert stats.unique_cards == 2

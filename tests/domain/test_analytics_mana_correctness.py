"""Regression tests for mana/analytics correctness with real-shaped
Scryfall cards: MDFC classification, produced-mana and fetch-land
sources, hybrid/Phyrexian pips, the land-count hint, commander
inclusion, and the Commander bracket estimate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.analytics import (
    compute_mana_base,
    compute_stats,
    count_mana_pips,
    estimate_bracket,
    is_commander_deck,
)
from vimtg.domain.card import Card, Color
from vimtg.domain.deck import Deck

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(
        (FIXTURES / name).read_text(encoding="utf-8")
    )
    return data


@pytest.fixture
def cards(real_shape_cards: list[dict[str, Any]]) -> dict[str, Card]:
    """Mana-analytics fixture plus the shared real-shape set, by name."""
    raw = real_shape_cards + _load("scryfall_mana_analytics.json")
    return {d["name"]: Card.from_scryfall(d) for d in raw}


def _deck(text: str) -> Deck:
    return parse_deck_text(text)


def _sources(check: Any) -> dict[Color, int]:
    return {r.color: r.sources for r in check.requirements}


# ── (a) MDFCs classified by front face ───────────────────────────


class TestFrontFaceLand:
    def test_mdfc_spell_is_not_a_land(self, cards: dict[str, Card]) -> None:
        assert not cards["Valakut Awakening // Valakut Stoneforge"].is_land
        assert not cards["Agadeem's Awakening // Agadeem, the Undercrypt"].is_land

    def test_pathway_and_basic_are_lands(self, cards: dict[str, Card]) -> None:
        assert cards["Brightclimb Pathway // Grimclimb Pathway"].is_land
        assert cards["Mountain"].is_land

    def test_mdfc_spells_counted_in_curve_not_lands(
        self, cards: dict[str, Card]
    ) -> None:
        deck = _deck(
            "4 Valakut Awakening // Valakut Stoneforge\n"
            "2 Agadeem's Awakening // Agadeem, the Undercrypt\n"
            "10 Mountain\n"
        )
        stats = compute_stats(deck, cards)
        assert stats.land_count == 10
        assert stats.nonland_count == 6
        assert stats.mana_curve.buckets[3] == 6

    def test_mana_base_land_total_excludes_mdfc_spells(
        self, cards: dict[str, Card]
    ) -> None:
        deck = _deck(
            "4 Valakut Awakening // Valakut Stoneforge\n"
            "4 Lightning Bolt\n"
            "10 Mountain\n"
        )
        check = compute_mana_base(deck, cards)
        assert check.total_lands == 10
        # The MDFC's produced_mana must not make it a red source
        assert _sources(check)[Color.RED] == 10


# ── (b) Sources from produced_mana and fetch text ────────────────


class TestManaSources:
    def test_command_tower_and_city_of_brass_count(
        self, cards: dict[str, Card]
    ) -> None:
        deck = _deck(
            "1 Lightning Helix\n1 Command Tower\n1 City of Brass\n"
        )
        sources = _sources(compute_mana_base(deck, cards))
        assert sources[Color.RED] == 2
        assert sources[Color.WHITE] == 2

    def test_typed_fetch_counts_for_its_types(
        self, cards: dict[str, Card]
    ) -> None:
        deck = _deck("4 Lightning Helix\n4 Arid Mesa\n1 Mountain\n1 Plains\n")
        sources = _sources(compute_mana_base(deck, cards))
        assert sources[Color.RED] == 5
        assert sources[Color.WHITE] == 5

    def test_basic_fetch_counts_for_basics_in_deck(
        self, cards: dict[str, Card]
    ) -> None:
        deck = _deck(
            "4 Lightning Helix\n4 Evolving Wilds\n6 Mountain\n"
        )
        sources = _sources(compute_mana_base(deck, cards))
        # Wilds finds a Mountain (R) but there is no Plains to find
        assert sources[Color.RED] == 10
        assert sources[Color.WHITE] == 0

    def test_basic_fetch_without_basics_finds_nothing(
        self, cards: dict[str, Card]
    ) -> None:
        deck = _deck("4 Lightning Helix\n4 Evolving Wilds\n")
        sources = _sources(compute_mana_base(deck, cards))
        assert sources == {Color.RED: 0, Color.WHITE: 0}

    def test_produced_plus_fetch(self, cards: dict[str, Card]) -> None:
        deck = _deck("1 Spectral Procession\n2 Krosan Verge\n1 Plains\n")
        sources = _sources(compute_mana_base(deck, cards))
        assert sources[Color.WHITE] == 3

    def test_no_false_shortfall_with_fetches(
        self, cards: dict[str, Card]
    ) -> None:
        deck = _deck(
            "4 Lightning Helix\n8 Arid Mesa\n6 Mountain\n6 Plains\n"
            + "36 Lightning Bolt\n"
        )
        check = compute_mana_base(deck, cards)
        assert all(r.satisfied for r in check.requirements)

    def test_old_database_without_produced_mana_falls_back(self) -> None:
        land = Card.from_scryfall({
            "id": "x", "name": "Sacred Foundry", "type_line":
            "Land — Mountain Plains", "color_identity": ["R", "W"],
        })
        spell = Card.from_scryfall({
            "id": "y", "name": "Boros Charm", "type_line": "Instant",
            "mana_cost": "{R}{W}", "cmc": 2.0,
        })
        deck = _deck("1 Boros Charm\n1 Sacred Foundry\n")
        sources = _sources(compute_mana_base(
            deck, {"Sacred Foundry": land, "Boros Charm": spell}
        ))
        assert sources == {Color.RED: 1, Color.WHITE: 1}


# ── (c) Hybrid and Phyrexian pips ────────────────────────────────


class TestHybridPhyrexianPips:
    def test_hybrid_counts_each_colour(self) -> None:
        assert count_mana_pips("{R/G}{R/G}{R/G}") == {
            Color.RED: 3, Color.GREEN: 3,
        }

    def test_phyrexian_counts_its_colour(self) -> None:
        assert count_mana_pips("{1}{B/P}{B/P}") == {Color.BLACK: 2}

    def test_hybrid_phyrexian(self) -> None:
        assert count_mana_pips("{G/U/P}") == {Color.GREEN: 1, Color.BLUE: 1}

    def test_two_brid(self) -> None:
        assert count_mana_pips("{2/W}{2/W}{2/W}") == {Color.WHITE: 3}

    def test_colorless_symbols_still_zero(self) -> None:
        assert count_mana_pips("{X}{C}{2}{S}") == {}

    def test_hybrid_card_produces_requirement(
        self, cards: dict[str, Card]
    ) -> None:
        deck = _deck("4 Boggart Ram-Gang\n4 Dismember\n10 Mountain\n")
        reqs = {r.color: r for r in compute_mana_base(deck, cards).requirements}
        assert reqs[Color.RED].pips == 12
        assert reqs[Color.GREEN].pips == 12
        assert reqs[Color.BLACK].pips == 8


# ── (d) Land hint scaled by format; commander included ───────────


class TestRecommendedLands:
    def test_sixty_card_hint(self, cards: dict[str, Card]) -> None:
        # avg MV 2.0 -> 19.59 + 1.90 * 2 = 23.39 -> 23
        deck = _deck("36 Lightning Helix\n24 Mountain\n")
        assert compute_stats(deck, cards).recommended_lands == 23

    def test_forty_card_limited_hint(self, cards: dict[str, Card]) -> None:
        # 23.39 * 40 / 60 = 15.6 -> 16
        deck = _deck("23 Lightning Helix\n17 Mountain\n")
        assert compute_stats(deck, cards).recommended_lands == 16

    def test_commander_hint_not_clamped(self, cards: dict[str, Card]) -> None:
        # 62 x MV 2 + Aurelia (MV 6): avg = 130 / 63 = 2.063
        # -> 31.42 + 3.13 * 2.063 = 37.9 -> 38 (the old clamp gave <= 28)
        deck = _deck(
            "CMD: 1 Aurelia, the Warleader\n62 Lightning Helix\n37 Mountain\n"
        )
        stats = compute_stats(deck, cards)
        assert stats.recommended_lands == 38

    def test_no_nonland_cards_no_hint(self) -> None:
        assert compute_stats(_deck(""), {}).recommended_lands is None

    def test_commander_in_totals_curve_and_pips(
        self, cards: dict[str, Card]
    ) -> None:
        deck = _deck("CMD: 1 Aurelia, the Warleader\n1 Lightning Helix\n")
        stats = compute_stats(deck, cards)
        assert stats.total_cards == 2
        assert stats.commander_count == 1
        assert stats.mainboard_count == 1
        assert stats.mana_curve.buckets[6] == 1
        assert stats.color_distribution.pips[Color.RED] == 3
        reqs = {r.color: r for r in compute_mana_base(deck, cards).requirements}
        assert reqs[Color.WHITE].pips == 3

    def test_price_source_recorded(self, cards: dict[str, Card]) -> None:
        deck = _deck("1 Aurelia, the Warleader\n")
        stats = compute_stats(deck, cards, "eur")
        assert stats.price_source == "eur"
        assert stats.total_price_usd == 4.0


# ── (e) Commander brackets ───────────────────────────────────────


class TestBracketEstimate:
    _GC4 = (
        "1 Smothering Tithe\n1 Enlightened Tutor\n1 Gamble\n"
        "1 Jeska's Will\n"
    )

    @pytest.mark.parametrize(
        ("n", "label"), [(0, "1-2"), (1, "3"), (3, "3"), (4, "4+")]
    )
    def test_labels(self, cards: dict[str, Card], n: int, label: str) -> None:
        lines = self._GC4.splitlines()[:n]
        deck = _deck("CMD: 1 Aurelia, the Warleader\n" + "\n".join(lines))
        est = estimate_bracket(deck, cards)
        assert est.count == n
        assert est.label == label

    def test_commander_and_duplicates_counted_once(
        self, cards: dict[str, Card]
    ) -> None:
        deck = _deck(
            "1 Smothering Tithe\n1 Smothering Tithe\nSB: 1 Gamble\n"
        )
        est = estimate_bracket(deck, cards)
        assert est.game_changers == ("Smothering Tithe",)

    def test_is_commander_deck(self) -> None:
        assert is_commander_deck(_deck("// Format: commander\n1 Sol Ring\n"))
        assert is_commander_deck(_deck("CMD: 1 Aurelia, the Warleader\n"))
        assert not is_commander_deck(_deck("// Format: modern\n4 Gamble\n"))
        assert not is_commander_deck(_deck("4 Gamble\n"))

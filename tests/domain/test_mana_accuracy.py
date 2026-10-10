"""Mana-analytics accuracy with real-shaped Scryfall cards: hybrid and
Phyrexian requirements, split-card costs and curve, and fetch lands
that only count for land types the deck holds."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.analytics import (
    ColorRequirement,
    compute_mana_base,
    compute_stats,
    count_mana_pips,
    curve_mana_value,
)
from vimtg.domain.card import Card, Color
from vimtg.domain.mana import (
    cost_halves,
    is_hybrid,
    is_phyrexian,
    mana_value,
    symbol_colors,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def cards(real_shape_cards: list[dict[str, Any]]) -> dict[str, Card]:
    raw: list[dict[str, Any]] = list(real_shape_cards)
    for name in (
        "scryfall_validation.json",  # Forest
        "scryfall_mana_analytics.json",
        "scryfall_mana_accuracy.json",
    ):
        raw += json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return {d["name"]: Card.from_scryfall(d) for d in raw}


def _reqs(text: str, cards: dict[str, Card]) -> dict[Color, ColorRequirement]:
    check = compute_mana_base(parse_deck_text(text), cards)
    return {r.color: r for r in check.requirements}


# ── mana helpers ──────────────────────────────────────────────────


class TestManaHelpers:
    @pytest.mark.parametrize(
        ("cost", "value"),
        [
            ("{1}{R}", 2.0),
            ("{2/W}{2/W}{2/W}", 6.0),
            ("{1}{G/W}{G/W}", 3.0),
            ("{1}{B/P}{B/P}", 3.0),
            ("{X}{R}", 1.0),
            ("{G/U/P}", 1.0),
            ("{HW}", 0.5),
            ("", 0.0),
        ],
    )
    def test_mana_value(self, cost: str, value: float) -> None:
        assert mana_value(cost) == value

    def test_symbol_kinds(self) -> None:
        assert is_hybrid("G/W") and is_hybrid("2/W") and is_hybrid("G/U/P")
        assert not is_hybrid("B/P") and not is_hybrid("R")
        assert is_phyrexian("B/P") and is_phyrexian("G/U/P")
        assert not is_phyrexian("G/W")
        assert symbol_colors("G/W") == (Color.WHITE, Color.GREEN)
        assert symbol_colors("2/W") == (Color.WHITE,)

    def test_cost_halves(self) -> None:
        assert cost_halves("{1}{R} // {1}{U}") == ("{1}{R}", "{1}{U}")
        assert cost_halves("{R}") == ("{R}",)


# ── (a) hybrid and Phyrexian ──────────────────────────────────────


class TestHybridRequirement:
    def test_kitchen_finks_in_green_white_splits_its_pips(
        self, cards: dict[str, Card]
    ) -> None:
        # Was: 18 G and 18 W asked for (two pips of each on turn 3).
        reqs = _reqs(
            "4 Kitchen Finks\n12 Forest\n12 Plains\n32 Island\n", cards
        )
        assert reqs[Color.GREEN].needed == 12
        assert reqs[Color.WHITE].needed == 12
        assert reqs[Color.GREEN].satisfied and reqs[Color.WHITE].satisfied

    def test_kitchen_finks_in_mono_green_asks_nothing_of_white(
        self, cards: dict[str, Card]
    ) -> None:
        reqs = _reqs("4 Kitchen Finks\n20 Forest\n36 Llanowar Elves\n", cards)
        assert reqs[Color.WHITE].needed == 0
        assert reqs[Color.WHITE].satisfied
        assert reqs[Color.GREEN].needed == 18  # both pips paid with green
        # pip totals still show every colour a hybrid symbol carries
        assert reqs[Color.WHITE].pips == 8

    def test_dismember_in_izzet_raises_no_black_requirement(
        self, cards: dict[str, Card]
    ) -> None:
        # Was: "need 18 more" black sources.
        reqs = _reqs(
            "4 Dismember\n4 Lightning Bolt\n12 Island\n12 Mountain\n28 Fire // Ice\n",
            cards,
        )
        black = reqs[Color.BLACK]
        assert black.pips == 8
        assert black.needed == 0 and black.satisfied

    def test_phyrexian_only_card_needs_no_source(self, cards: dict[str, Card]) -> None:
        reqs = _reqs("4 Gitaxian Probe\n20 Mountain\n", cards)
        assert reqs[Color.BLUE].needed == 0

    def test_two_brid_payable_with_generic(self, cards: dict[str, Card]) -> None:
        reqs = _reqs("4 Spectral Procession\n20 Mountain\n", cards)
        assert reqs[Color.WHITE].needed == 0

    def test_hard_pips_still_count(self, cards: dict[str, Card]) -> None:
        reqs = _reqs("4 Gaddock Teeg\n20 Forest\n36 Llanowar Elves\n", cards)
        assert reqs[Color.WHITE].needed == 13
        assert not reqs[Color.WHITE].satisfied

    def test_pip_totals_unchanged(self) -> None:
        assert count_mana_pips("{1}{G/W}{G/W}") == {Color.GREEN: 2, Color.WHITE: 2}
        assert count_mana_pips("{1}{B/P}{B/P}") == {Color.BLACK: 2}


# ── (b)/(g) split cards ───────────────────────────────────────────


class TestSplitCards:
    def test_split_card_stores_both_halves(self, cards: dict[str, Card]) -> None:
        assert cards["Fire // Ice"].mana_cost == "{1}{R} // {1}{U}"
        assert cards["Wear // Tear"].mana_cost == "{1}{R} // {W}"
        assert cards["Commit // Memory"].mana_cost == "{3}{U} // {4}{W}{W}"

    def test_split_cost_from_faces_when_top_level_missing(
        self, real_shape_cards: list[dict[str, Any]]
    ) -> None:
        raw = next(d for d in real_shape_cards if d["name"] == "Fire // Ice")
        raw = {k: v for k, v in raw.items() if k != "mana_cost"}
        raw["mana_cost"] = ""
        assert Card.from_scryfall(raw).mana_cost == "{1}{R} // {1}{U}"

    def test_pips_count_both_halves(self, cards: dict[str, Card]) -> None:
        assert count_mana_pips(cards["Wear // Tear"].mana_cost) == {
            Color.RED: 1, Color.WHITE: 1,
        }

    def test_each_half_raises_its_own_requirement(
        self, cards: dict[str, Card]
    ) -> None:
        reqs = _reqs("4 Commit // Memory\n20 Island\n36 Lightning Bolt\n", cards)
        # Memory: WW on turn 6 -> 14 white sources; Commit: U on turn 4
        assert reqs[Color.WHITE].needed == 14
        assert reqs[Color.BLUE].needed == 11
        assert reqs[Color.WHITE].pips == 8

    def test_curve_uses_cheaper_half(self, cards: dict[str, Card]) -> None:
        assert curve_mana_value(cards["Fire // Ice"]) == 2.0
        assert curve_mana_value(cards["Commit // Memory"]) == 4.0
        assert curve_mana_value(cards["Lightning Bolt"]) == 1.0
        stats = compute_stats(parse_deck_text("4 Fire // Ice\n4 Wear // Tear\n"), cards)
        # Fire // Ice at 2 (not 4), Wear // Tear at 1 (not 3)
        assert stats.mana_curve.buckets[2] == 4
        assert stats.mana_curve.buckets[1] == 4
        assert stats.mana_curve.buckets[4] == 0
        assert stats.average_cmc == 1.5

    def test_land_hint_uses_curve_value(self, cards: dict[str, Card]) -> None:
        stats = compute_stats(parse_deck_text("60 Fire // Ice\n"), cards)
        assert stats.recommended_lands == round(19.59 + 1.90 * 2.0)


# ── (c) fetch lands ───────────────────────────────────────────────


class TestFetchLands:
    def test_delta_is_no_black_source_without_swamp_types(
        self, cards: dict[str, Card]
    ) -> None:
        reqs = _reqs(
            "4 Dismember\n4 Fire // Ice\n4 Polluted Delta\n4 Island\n8 Mountain\n",
            cards,
        )
        assert reqs[Color.BLACK].sources == 0
        assert reqs[Color.BLUE].sources == 8

    def test_delta_finds_dual_types(self, cards: dict[str, Card]) -> None:
        reqs = _reqs(
            "4 Dismember\n4 Lightning Bolt\n4 Polluted Delta\n2 Steam Vents\n"
            "1 Watery Grave\n",
            cards,
        )
        # Steam Vents (an Island) makes the Delta a red source too;
        # Watery Grave (a Swamp) a black one.
        assert reqs[Color.RED].sources == 6
        assert reqs[Color.BLACK].sources == 5

    def test_basic_fetch_ignores_nonbasic_duals(self, cards: dict[str, Card]) -> None:
        reqs = _reqs(
            "4 Lightning Bolt\n4 Evolving Wilds\n2 Steam Vents\n", cards
        )
        assert reqs[Color.RED].sources == 2

    def test_sideboard_lands_are_not_fetch_targets(self, cards: dict[str, Card]) -> None:
        reqs = _reqs(
            "4 Dismember\n4 Fire // Ice\n4 Polluted Delta\nSB: 1 Watery Grave\n", cards
        )
        assert reqs[Color.BLACK].sources == 0

    def test_tutor_text_is_not_a_fetch(self, cards: dict[str, Card]) -> None:
        # "Search your library for a card" on a land finds no colour
        tutor_land = Card.from_scryfall(
            {
                "id": "tutor-land", "name": "Tutor Land", "layout": "normal",
                "type_line": "Land", "mana_cost": "", "cmc": 0.0,
                "oracle_text": "{T}, Sacrifice Tutor Land: Search your library "
                "for a card, put it into your hand, then shuffle.",
                "set": "tst", "rarity": "rare",
            }
        )
        deck = parse_deck_text("4 Lightning Bolt\n4 Tutor Land\n4 Mountain\n")
        check = compute_mana_base(deck, {**cards, "Tutor Land": tutor_land})
        assert {r.color: r.sources for r in check.requirements}[Color.RED] == 4

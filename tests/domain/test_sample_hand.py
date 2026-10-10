"""Sample hand / goldfish logic: library building, London mulligan,
drawing, seeded determinism, and hypergeometric land odds."""

from __future__ import annotations

import json
import random
from collections import Counter
from math import comb
from pathlib import Path

import pytest

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.domain.sample_hand import (
    Goldfish,
    GoldfishError,
    HandSource,
    bottom_count,
    build_source,
    count_lands,
    deal,
    draw,
    format_hand,
    format_odds,
    hand_odds,
    land_names,
    mulligan,
    put_on_bottom,
    source_odds,
)
from vimtg.domain.sideboard_plan import find_plan

FIXTURES = Path(__file__).parent.parent / "fixtures"

BURN = """\
// Deck: Burn
// Format: modern

DCK:
4 Lightning Bolt
4 Goblin Guide
4 Sacred Foundry
16 Mountain
32 Lava Spike

SB: 4 Skullcrack
MB: 0 Nothing

VS: Tron
    -4 Goblin Guide
    +4 Skullcrack
"""

COMMANDER = """\
// Deck: Atraxa
// Format: commander

CMD: 1 Atraxa, Praetors' Voice
CMP: 1 Lurrus of the Dream-Den

DCK:
37 Forest
62 Llanowar Elves

SB: 1 Maybe Card
"""


@pytest.fixture
def resolved() -> dict[str, Card]:
    with open(FIXTURES / "scryfall_sample.json") as f:
        cards = [Card.from_scryfall(d) for d in json.load(f)]
    return {c.name: c for c in cards}


def _source(n: int = 60, lands: int = 24) -> HandSource:
    library = tuple(["Land"] * lands + [f"Spell {i}" for i in range(n - lands)])
    return HandSource(library=library, lands=frozenset({"Land"}))


# ── Library building ──────────────────────────────────────


class TestBuildSource:
    def test_main_deck_only_respecting_quantities(self) -> None:
        source = build_source(parse_deck_text(BURN))
        counts = Counter(source.library)
        assert counts == {
            "Lightning Bolt": 4, "Goblin Guide": 4, "Sacred Foundry": 4,
            "Mountain": 16, "Lava Spike": 32,
        }
        assert "Skullcrack" not in counts

    def test_sideboard_maybeboard_excluded(self) -> None:
        deck = parse_deck_text(
            "DCK:\n4 Mountain\nSB: 2 Duress\n// Maybeboard\nMB: 3 Shock\n"
        )
        source = build_source(deck)
        assert Counter(source.library) == {"Mountain": 4}

    def test_commander_goes_to_command_zone(self) -> None:
        source = build_source(parse_deck_text(COMMANDER), fmt="commander")
        assert source.command_zone == ("Atraxa, Praetors' Voice",)
        assert source.companions == ("Lurrus of the Dream-Den",)
        assert len(source.library) == 99
        assert "Atraxa, Praetors' Voice" not in source.library
        assert "Lurrus of the Dream-Den" not in source.library
        assert "Maybe Card" not in source.library

    def test_plan_boards_the_deck(self) -> None:
        deck = parse_deck_text(BURN)
        plan = find_plan(deck, "tron")
        assert plan is not None
        source = build_source(deck, plan=plan)
        counts = Counter(source.library)
        assert counts["Skullcrack"] == 4
        assert "Goblin Guide" not in counts
        assert len(source.library) == 60
        assert source.plan == "Tron"

    def test_no_plan_name_without_plan(self) -> None:
        assert build_source(parse_deck_text(BURN)).plan == ""

    def test_lands_from_resolved_type_line(self, resolved: dict[str, Card]) -> None:
        source = build_source(parse_deck_text(BURN), resolved)
        assert source.lands == {"Sacred Foundry", "Mountain"}
        assert source.land_count == 20

    def test_resolved_lookup_ignores_case(self, resolved: dict[str, Card]) -> None:
        assert land_names(frozenset({"sacred foundry"}), resolved) == {"sacred foundry"}

    def test_basic_lands_known_without_database(self) -> None:
        source = build_source(parse_deck_text(BURN))
        assert source.lands == {"Mountain"}
        assert source.land_count == 16

    @pytest.mark.parametrize(
        ("fmt", "free"),
        [
            ("commander", True), ("Commander", True), ("brawl", True),
            ("standardbrawl", True), ("oathbreaker", True),
            ("paupercommander", True), ("duel", False), ("modern", False),
        ],
    )
    def test_free_mulligan_by_format(self, fmt: str, free: bool) -> None:
        assert build_source(parse_deck_text(BURN), fmt=fmt).free_mulligan is free

    def test_unformatted_deck_with_commander_gets_free_mulligan(self) -> None:
        deck = parse_deck_text("CMD: 1 Atraxa, Praetors' Voice\nDCK:\n99 Forest\n")
        assert build_source(deck).free_mulligan is True
        assert build_source(parse_deck_text(BURN), fmt="").free_mulligan is False

    def test_empty_deck(self) -> None:
        source = build_source(parse_deck_text("// Deck: Empty\n"))
        assert source.library == ()
        assert source.land_count == 0


# ── Dealing and drawing ───────────────────────────────────


class TestDeal:
    def test_opening_seven(self) -> None:
        source = _source()
        state = deal(source.library, random.Random(1))
        assert len(state.hand) == 7
        assert len(state.library) == 53
        assert Counter(state.cards()) == Counter(source.library)
        assert state.kept and state.mulligans == 0 and state.draws == 0

    def test_seed_is_deterministic(self) -> None:
        lib = _source().library
        a = deal(lib, random.Random(42))
        b = deal(lib, random.Random(42))
        assert a == b

    def test_different_seeds_differ(self) -> None:
        lib = tuple(f"Card {i}" for i in range(60))
        hands = {deal(lib, random.Random(s)).hand for s in range(10)}
        assert len(hands) > 1

    def test_input_order_unchanged(self) -> None:
        lib = ["a", "b", "c", "d", "e", "f", "g", "h"]
        deal(lib, random.Random(3))
        assert lib == ["a", "b", "c", "d", "e", "f", "g", "h"]

    def test_small_library_deals_what_it_has(self) -> None:
        state = deal(("a", "b", "c"), random.Random(0))
        assert sorted(state.hand) == ["a", "b", "c"]
        assert state.library == ()

    def test_empty_library(self) -> None:
        state = deal((), random.Random(0))
        assert state.hand == () and state.library == ()

    def test_draw_takes_top_card(self) -> None:
        state = deal(_source().library, random.Random(5))
        top = state.library[0]
        drawn = draw(state)
        assert drawn.hand == state.hand + (top,)
        assert drawn.library == state.library[1:]
        assert drawn.draws == 1

    def test_draw_from_empty_library(self) -> None:
        state = deal(("a",), random.Random(0))
        with pytest.raises(GoldfishError, match="empty"):
            draw(state)

    def test_draw_blocked_until_bottomed(self) -> None:
        state = mulligan(deal(_source().library, random.Random(0)), random.Random(0))
        with pytest.raises(GoldfishError, match="bottom first"):
            draw(state)


# ── London mulligan ───────────────────────────────────────


class TestMulligan:
    def test_draws_seven_then_owes_one(self) -> None:
        rng = random.Random(7)
        state = mulligan(deal(_source().library, rng), rng)
        assert len(state.hand) == 7
        assert state.mulligans == 1
        assert state.to_bottom == 1
        assert not state.kept
        assert len(state.cards()) == 60

    def test_second_mulligan_owes_two(self) -> None:
        rng = random.Random(7)
        state = mulligan(mulligan(deal(_source().library, rng), rng), rng)
        assert state.mulligans == 2 and state.to_bottom == 2

    def test_first_mulligan_free_in_multiplayer(self) -> None:
        rng = random.Random(7)
        state = deal(_source().library, rng, free_mulligan=True)
        state = mulligan(state, rng)
        assert state.to_bottom == 0 and state.kept
        state = mulligan(state, rng)
        assert state.to_bottom == 1

    def test_bottom_puts_card_under_library(self) -> None:
        rng = random.Random(7)
        state = mulligan(deal(_source().library, rng), rng)
        card = state.hand[3]
        state = put_on_bottom(state, 3)
        assert len(state.hand) == 6
        assert state.library[-1] == card
        assert state.bottomed == (card,)
        assert state.kept
        # Now drawing works and never draws the bottomed card first
        assert draw(state).hand[-1] == state.library[0]

    def test_bottom_requires_a_debt(self) -> None:
        state = deal(_source().library, random.Random(0))
        with pytest.raises(GoldfishError, match="No cards to put"):
            put_on_bottom(state, 0)

    @pytest.mark.parametrize("index", [-1, 7, 99])
    def test_bottom_index_out_of_range(self, index: int) -> None:
        rng = random.Random(0)
        state = mulligan(deal(_source().library, rng), rng)
        with pytest.raises(GoldfishError, match="No card selected"):
            put_on_bottom(state, index)

    def test_no_mulligan_after_drawing(self) -> None:
        state = draw(deal(_source().library, random.Random(0)))
        with pytest.raises(GoldfishError, match="already kept"):
            mulligan(state, random.Random(0))

    def test_no_mulligan_after_bottoming(self) -> None:
        rng = random.Random(0)
        state = mulligan(mulligan(deal(_source().library, rng), rng), rng)
        state = put_on_bottom(state, 0)
        with pytest.raises(GoldfishError, match="already kept"):
            mulligan(state, rng)

    def test_cannot_mulligan_below_zero(self) -> None:
        rng = random.Random(0)
        state = deal(_source().library, rng)
        for _ in range(7):
            state = mulligan(state, rng)
        assert state.to_bottom == 7
        with pytest.raises(GoldfishError, match="below zero"):
            mulligan(state, rng)

    def test_bottom_debt_capped_by_hand_size(self) -> None:
        rng = random.Random(0)
        state = deal(("a", "b", "c"), rng)
        state = mulligan(mulligan(state, rng), rng)
        assert state.to_bottom == 2
        state = mulligan(state, rng)
        assert state.to_bottom == 3
        with pytest.raises(GoldfishError, match="below zero"):
            mulligan(state, rng)

    def test_mulligan_empty_game(self) -> None:
        with pytest.raises(GoldfishError, match="No cards"):
            mulligan(Goldfish(hand=(), library=()), random.Random(0))

    @pytest.mark.parametrize(
        ("mulligans", "free", "expected"),
        [(0, False, 0), (1, False, 1), (3, False, 3), (0, True, 0), (1, True, 0), (2, True, 1)],
    )
    def test_bottom_count(self, mulligans: int, free: bool, expected: int) -> None:
        assert bottom_count(mulligans, free) == expected

    def test_mulligan_is_seeded(self) -> None:
        lib = _source().library

        def run() -> Goldfish:
            rng = random.Random(99)
            return mulligan(deal(lib, rng), rng)

        assert run() == run()


# ── Odds ──────────────────────────────────────────────────


class TestOdds:
    def test_matches_hypergeometric(self) -> None:
        odds = hand_odds(60, 24)
        none = comb(36, 7) / comb(60, 7)
        one = 24 * comb(36, 6) / comb(60, 7)
        assert odds.one_land == pytest.approx(1 - none)
        assert odds.two_lands == pytest.approx(1 - none - one)

    def test_known_values(self) -> None:
        # 24 lands in 60, computed independently: 1 - C(36,7)/C(60,7), etc.
        odds = hand_odds(60, 24)
        assert odds.one_land == pytest.approx(0.9784, abs=1e-4)
        assert odds.two_lands == pytest.approx(0.8573, abs=1e-4)

    def test_land_drops_play_vs_draw(self) -> None:
        odds = hand_odds(60, 24, turns=4)
        assert [d.turn for d in odds.land_drops] == [1, 2, 3, 4]
        first = odds.land_drops[0]
        # Turn 1 on the play sees 7 cards, on the draw 8
        assert first.on_the_play == pytest.approx(odds.one_land)
        assert first.on_the_draw > first.on_the_play
        for d in odds.land_drops:
            assert d.on_the_draw >= d.on_the_play
        plays = [d.on_the_play for d in odds.land_drops]
        assert plays == sorted(plays, reverse=True)

    def test_no_lands(self) -> None:
        odds = hand_odds(60, 0)
        assert odds.one_land == 0.0 and odds.two_lands == 0.0
        assert all(d.on_the_play == 0.0 for d in odds.land_drops)

    def test_all_lands(self) -> None:
        odds = hand_odds(40, 40)
        assert odds.one_land == 1.0 and odds.two_lands == 1.0

    def test_empty_deck(self) -> None:
        odds = hand_odds(0, 0)
        assert odds.one_land == 0.0

    def test_source_odds_uses_library(self) -> None:
        odds = source_odds(_source(99, 37))
        assert odds.deck_size == 99 and odds.land_count == 37

    def test_format_odds(self) -> None:
        lines = format_odds(hand_odds(60, 24, turns=2))
        assert lines[0] == "Lands: 24 of 60"
        assert lines[1] == "P(>=1 land in 7): 97.8%"
        assert lines[2] == "P(>=2 lands in 7): 85.7%"
        assert len(lines) == 5 + 2  # header rows + one per turn


# ── Text rendering ────────────────────────────────────────


class TestFormatHand:
    def test_lists_hand_land_count_and_odds(self) -> None:
        source = build_source(parse_deck_text(BURN))
        state = deal(source.library, random.Random(42))
        text = format_hand(source, state, seed=42)
        lands = count_lands(state.hand, source.lands)
        noun = "land" if lands == 1 else "lands"
        assert f"Opening hand (7 cards, {lands} {noun})  seed=42:" in text
        for name in state.hand:
            assert f"  {name}\n" in text
        assert "P(>=1 land in 7)" in text

    def test_shows_draws_separately(self) -> None:
        source = build_source(parse_deck_text(BURN))
        state = draw(draw(deal(source.library, random.Random(1))))
        text = format_hand(source, state)
        assert "Opening hand (7 cards" in text
        assert f"Draws:\n  1. {state.hand[7]}\n  2. {state.hand[8]}\n" in text
        assert "seed=" not in text

    def test_shows_zones_and_plan(self) -> None:
        source = build_source(parse_deck_text(COMMANDER), fmt="commander")
        text = format_hand(source, deal(source.library, random.Random(0)))
        assert "Command zone: Atraxa, Praetors' Voice" in text
        assert "Companion: Lurrus of the Dream-Den" in text
        deck = parse_deck_text(BURN)
        boarded = build_source(deck, plan=find_plan(deck, "Tron"))
        assert format_hand(boarded, deal(boarded.library, random.Random(0))).startswith(
            "Plan: vs Tron\n"
        )

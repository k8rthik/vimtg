"""Sample hands and goldfishing — draw 7, London mulligan, draw on.

Pure logic over a Deck: which cards make up the library (the mainboard;
for Commander the 99, with the commander set aside in the command
zone), a shuffled game state that supports the London mulligan and
drawing, and hypergeometric land odds for the opener and land drops.

Randomness comes in through a caller-supplied ``random.Random``, so a
seeded generator gives the same hands every time (``:hand seed=42``).

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from vimtg.domain.card import Card
from vimtg.domain.card_names import CardMap
from vimtg.domain.card_types import is_basic_land
from vimtg.domain.deck import Deck, DeckSection
from vimtg.domain.formats import normalize_format
from vimtg.domain.probabilities import OPENING_HAND_SIZE, draws_by_turn, prob_at_least
from vimtg.domain.sideboard_plan import SideboardPlan, apply_plan

# CR 103.5c: the first mulligan is free in multiplayer games and in any
# Brawl game. Duel Commander is a two-player format, so it has no free one.
FREE_MULLIGAN_FORMATS = frozenset({
    "commander", "brawl", "standardbrawl", "oathbreaker", "paupercommander",
})

ODDS_TURNS = 5  # land-drop odds shown for turns 1..ODDS_TURNS


class GoldfishError(ValueError):
    """An action the current game state does not allow (shown to the user)."""


@dataclass(frozen=True)
class HandSource:
    """What a sample hand is drawn from.

    library: one name per physical card, in deck order (unshuffled).
    command_zone / companions: cards that start outside the library.
    lands: names in the library that count as lands.
    """

    library: tuple[str, ...]
    command_zone: tuple[str, ...] = ()
    companions: tuple[str, ...] = ()
    lands: frozenset[str] = frozenset()
    free_mulligan: bool = False
    plan: str = ""

    @property
    def land_count(self) -> int:
        return sum(1 for name in self.library if name in self.lands)


def _expand(deck: Deck, section: DeckSection) -> tuple[str, ...]:
    return tuple(
        e.card_name
        for e in deck.entries
        if e.section == section
        for _ in range(max(0, e.quantity))
    )


def land_names(
    names: frozenset[str], resolved: Mapping[str, Card] | None
) -> frozenset[str]:
    """The names that are lands: by resolved type line, else basic-land name.

    Without a card database only basic lands are known, so the odds
    undercount nonbasic lands until ``vimtg sync`` has run.
    """
    cards = CardMap(resolved) if resolved else CardMap()
    lands: set[str] = set()
    for name in names:
        card = cards.get(name)
        if (card is not None and card.is_land) or is_basic_land(name):
            lands.add(name)
    return frozenset(lands)


def build_source(
    deck: Deck,
    resolved: Mapping[str, Card] | None = None,
    fmt: str = "",
    plan: SideboardPlan | None = None,
) -> HandSource:
    """The library and side zones for goldfishing `deck`.

    Only the mainboard is shuffled: sideboard, maybeboard, commander
    and companion cards never start in the library. With `plan` the
    post-board mainboard is used. `fmt` (the effective format) decides
    whether the first mulligan is free; a deck with no format but a
    commander is treated as Commander.
    """
    if plan is not None:
        deck = apply_plan(deck, plan)
    library = _expand(deck, DeckSection.MAIN)
    command_zone = _expand(deck, DeckSection.COMMANDER)
    fmt = normalize_format(fmt)  # 'EDH', 'Standard Brawl' count too
    free = fmt in FREE_MULLIGAN_FORMATS or (not fmt and bool(command_zone))
    return HandSource(
        library=library,
        command_zone=command_zone,
        companions=_expand(deck, DeckSection.COMPANION),
        lands=land_names(frozenset(library), resolved),
        free_mulligan=free,
        plan=plan.name if plan is not None else "",
    )


# ── Game state ────────────────────────────────────────────


@dataclass(frozen=True)
class Goldfish:
    """One sample game: the hand, the library (index 0 is the top),
    and where the London mulligan stands.

    to_bottom: cards still owed to the bottom after a mulligan; the
    hand is kept (and drawing allowed) once it reaches 0.
    """

    hand: tuple[str, ...]
    library: tuple[str, ...]
    mulligans: int = 0
    to_bottom: int = 0
    bottomed: tuple[str, ...] = ()
    draws: int = 0
    free_mulligan: bool = False

    @property
    def kept(self) -> bool:
        return self.to_bottom == 0

    def cards(self) -> tuple[str, ...]:
        """Every card in the game (hand, library and bottomed)."""
        return self.hand + self.library


def bottom_count(mulligans: int, free_mulligan: bool) -> int:
    """Cards a London mulligan puts on the bottom after `mulligans`."""
    return max(0, mulligans - (1 if free_mulligan else 0))


def deal(
    cards: Sequence[str],
    rng: random.Random,
    *,
    free_mulligan: bool = False,
    mulligans: int = 0,
) -> Goldfish:
    """Shuffle `cards` and draw an opening hand of seven.

    A library smaller than seven deals what it has. `mulligans` is the
    number already taken; the London mulligan's bottom count follows it.
    """
    library = list(cards)
    rng.shuffle(library)
    size = min(OPENING_HAND_SIZE, len(library))
    hand = tuple(library[:size])
    return Goldfish(
        hand=hand,
        library=tuple(library[size:]),
        mulligans=mulligans,
        to_bottom=min(len(hand), bottom_count(mulligans, free_mulligan)),
        free_mulligan=free_mulligan,
    )


def mulligan(state: Goldfish, rng: random.Random) -> Goldfish:
    """London mulligan: shuffle everything back, draw seven again, then
    owe one more card to the bottom (the first is free in multiplayer)."""
    if state.draws or state.bottomed:
        raise GoldfishError("Hand already kept (r to start over)")
    if state.hand and state.to_bottom >= len(state.hand):
        raise GoldfishError("Cannot mulligan below zero cards")
    if not state.cards():
        raise GoldfishError("No cards to mulligan")
    return deal(
        state.cards(),
        rng,
        free_mulligan=state.free_mulligan,
        mulligans=state.mulligans + 1,
    )


def put_on_bottom(state: Goldfish, index: int) -> Goldfish:
    """Put the hand's `index`-th card on the bottom of the library."""
    if state.to_bottom <= 0:
        raise GoldfishError("No cards to put on the bottom")
    if not 0 <= index < len(state.hand):
        raise GoldfishError("No card selected")
    card = state.hand[index]
    return replace(
        state,
        hand=state.hand[:index] + state.hand[index + 1:],
        library=state.library + (card,),
        to_bottom=state.to_bottom - 1,
        bottomed=state.bottomed + (card,),
    )


def draw(state: Goldfish) -> Goldfish:
    """Draw the top card of the library into the hand."""
    if state.to_bottom:
        raise GoldfishError(
            f"Put {state.to_bottom} card{'s' if state.to_bottom != 1 else ''} "
            "on the bottom first (b)"
        )
    if not state.library:
        raise GoldfishError("Library is empty")
    return replace(
        state,
        hand=state.hand + (state.library[0],),
        library=state.library[1:],
        draws=state.draws + 1,
    )


def count_lands(cards: Sequence[str], lands: frozenset[str]) -> int:
    return sum(1 for name in cards if name in lands)


# ── Odds ──────────────────────────────────────────────────


@dataclass(frozen=True)
class LandDrop:
    """Chance of having made a land drop every turn through `turn`."""

    turn: int
    on_the_play: float
    on_the_draw: float


@dataclass(frozen=True)
class HandOdds:
    deck_size: int
    land_count: int
    one_land: float  # P(>= 1 land in the opening seven)
    two_lands: float  # P(>= 2 lands in the opening seven)
    land_drops: tuple[LandDrop, ...]


def hand_odds(
    deck_size: int, land_count: int, turns: int = ODDS_TURNS
) -> HandOdds:
    """Hypergeometric odds for the opener and land drops by turn.

    Hitting the turn-N land drop means at least N lands among the cards
    seen by turn N (seven plus a draw per turn, none on turn 1 on the
    play). Mulligans are ignored: these are the odds of a 7-card hand.
    """

    def p(k: int, draws: int) -> float:
        return prob_at_least(k, land_count, deck_size, draws)

    return HandOdds(
        deck_size=deck_size,
        land_count=land_count,
        one_land=p(1, OPENING_HAND_SIZE),
        two_lands=p(2, OPENING_HAND_SIZE),
        land_drops=tuple(
            LandDrop(
                turn=t,
                on_the_play=p(t, draws_by_turn(t, on_the_play=True)),
                on_the_draw=p(t, draws_by_turn(t)),
            )
            for t in range(1, turns + 1)
        ),
    )


def source_odds(source: HandSource, turns: int = ODDS_TURNS) -> HandOdds:
    return hand_odds(len(source.library), source.land_count, turns)


# ── Text rendering (CLI) ──────────────────────────────────


def _pct(p: float) -> str:
    return f"{p * 100:.1f}%"


def format_odds(odds: HandOdds) -> list[str]:
    """Odds as plain text lines, shared by the CLI and the overlay."""
    lines = [
        f"Lands: {odds.land_count} of {odds.deck_size}",
        f"P(>=1 land in 7): {_pct(odds.one_land)}",
        f"P(>=2 lands in 7): {_pct(odds.two_lands)}",
        "Land drop every turn through turn N:",
        f"  {'turn':<6}{'play':>8}{'draw':>8}",
    ]
    lines.extend(
        f"  {d.turn:<6}{_pct(d.on_the_play):>8}{_pct(d.on_the_draw):>8}"
        for d in odds.land_drops
    )
    return lines


def format_hand(
    source: HandSource, state: Goldfish, seed: int | None = None
) -> str:
    """A sample hand as text: zones, the hand, land count and odds."""
    lines: list[str] = []
    if source.plan:
        lines.append(f"Plan: vs {source.plan}")
    if source.command_zone:
        lines.append(f"Command zone: {', '.join(source.command_zone)}")
    if source.companions:
        lines.append(f"Companion: {', '.join(source.companions)}")
    opener = state.hand[: len(state.hand) - state.draws]
    lands = count_lands(opener, source.lands)
    header = f"Opening hand ({len(opener)} cards, {lands} land{'s' if lands != 1 else ''})"
    if seed is not None:
        header += f"  seed={seed}"
    lines.append(header + ":")
    lines.extend(f"  {name}" for name in opener)
    if state.draws:
        lines.append("Draws:")
        drawn = state.hand[len(opener):]
        lines.extend(f"  {i}. {name}" for i, name in enumerate(drawn, start=1))
    lines.append("")
    lines.extend(format_odds(source_odds(source)))
    return "\n".join(lines) + "\n"

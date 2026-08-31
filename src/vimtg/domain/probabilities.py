"""Hypergeometric draw probabilities for deck analytics.

Pure math, no card knowledge: given how many copies a deck runs, the
chance of seeing them in an opening hand or by a given turn.
"""

from __future__ import annotations

from math import comb

OPENING_HAND_SIZE = 7


def prob_at_least(
    k: int, copies: int, deck_size: int, draws: int
) -> float:
    """P(at least `k` of `copies` successes in `draws` from `deck_size`).

    Degenerate inputs (empty deck, no draws) yield 0.0 rather than
    raising — analytics render partial decks without ceremony.
    """
    if k <= 0:
        return 1.0
    if copies <= 0 or deck_size <= 0 or draws <= 0:
        return 0.0
    draws = min(draws, deck_size)
    copies = min(copies, deck_size)
    if k > min(copies, draws):
        return 0.0
    total = comb(deck_size, draws)
    missed = sum(
        comb(copies, i) * comb(deck_size - copies, draws - i)
        for i in range(k)
        if draws - i <= deck_size - copies
    )
    return 1.0 - missed / total


def draws_by_turn(turn: int, on_the_play: bool = False) -> int:
    """Cards seen by the end of `turn`: the opener plus one draw per
    turn (the play skips the first draw)."""
    draws = OPENING_HAND_SIZE + max(0, turn)
    return draws - 1 if on_the_play and turn > 0 else draws

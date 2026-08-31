"""Tests for hypergeometric draw probabilities."""

from __future__ import annotations

import pytest

from vimtg.domain.probabilities import prob_at_least

OPENING_HAND = 7


class TestProbAtLeast:
    def test_four_of_in_opener(self) -> None:
        # Classic result: a 4-of shows up in ~40% of 7-card openers
        p = prob_at_least(1, copies=4, deck_size=60, draws=OPENING_HAND)
        assert p == pytest.approx(0.3995, abs=1e-4)

    def test_two_plus_lands_in_opener(self) -> None:
        # 24 lands in 60: P(>=2 in the opener) ~ 85.7%
        p = prob_at_least(2, copies=24, deck_size=60, draws=OPENING_HAND)
        assert p == pytest.approx(0.8573, abs=1e-4)

    def test_zero_copies_is_zero(self) -> None:
        assert prob_at_least(1, copies=0, deck_size=60, draws=7) == 0.0

    def test_k_zero_is_certain(self) -> None:
        assert prob_at_least(0, copies=4, deck_size=60, draws=7) == 1.0

    def test_draws_capped_at_deck_size(self) -> None:
        # Drawing the whole deck finds every copy
        p = prob_at_least(4, copies=4, deck_size=60, draws=99)
        assert p == pytest.approx(1.0)

    def test_more_draws_never_hurts(self) -> None:
        p7 = prob_at_least(1, copies=4, deck_size=60, draws=7)
        p10 = prob_at_least(1, copies=4, deck_size=60, draws=10)
        assert p10 > p7

    def test_impossible_k_is_zero(self) -> None:
        assert prob_at_least(5, copies=4, deck_size=60, draws=7) == 0.0

    def test_singleton_in_commander_deck(self) -> None:
        # 1-of in 99 cards, 7-card opener: 7/99
        p = prob_at_least(1, copies=1, deck_size=99, draws=7)
        assert p == pytest.approx(7 / 99, abs=1e-6)

    def test_invalid_inputs_are_zero(self) -> None:
        assert prob_at_least(1, copies=4, deck_size=0, draws=7) == 0.0
        assert prob_at_least(1, copies=4, deck_size=60, draws=0) == 0.0

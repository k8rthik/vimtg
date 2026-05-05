"""Tests for fuzzy command completion engine."""

from __future__ import annotations

import pytest

from vimtg.editor.command_completer import (
    CommandCompleter,
    CompletionState,
    fuzzy_score,
)
from vimtg.editor.commands import CommandRegistry


# ── fuzzy_score ──────────────────────────────────────────────────


class TestFuzzyScore:
    def test_exact_match(self) -> None:
        assert fuzzy_score("sort", "sort") is not None
        # Exact match = prefix bonus applied, should be negative
        assert fuzzy_score("sort", "sort") == -4

    def test_prefix_match(self) -> None:
        score = fuzzy_score("so", "sort")
        assert score is not None
        assert score < 0  # prefix bonus

    def test_subsequence_match(self) -> None:
        score = fuzzy_score("st", "sort")
        assert score is not None
        # s at 0, t at 3 — gap of 2, first pos 0 → score 2
        assert score == 2

    def test_no_match(self) -> None:
        assert fuzzy_score("xyz", "sort") is None

    def test_case_insensitive(self) -> None:
        assert fuzzy_score("SO", "sort") is not None
        assert fuzzy_score("so", "Sort") is not None

    def test_empty_query_matches_everything(self) -> None:
        assert fuzzy_score("", "sort") == 0

    def test_prefix_ranked_above_subsequence(self) -> None:
        prefix_score = fuzzy_score("so", "sort")
        subseq_score = fuzzy_score("st", "sort")
        assert prefix_score is not None
        assert subseq_score is not None
        assert prefix_score < subseq_score

    def test_query_longer_than_candidate(self) -> None:
        assert fuzzy_score("sorting", "sort") is None


# ── CommandCompleter ─────────────────────────────────────────────


def _make_registry() -> CommandRegistry:
    """Build a small registry for testing."""
    reg = CommandRegistry()
    reg.register("write", lambda *a: (a[0], a[1]), aliases=["w"])
    reg.register("quit", lambda *a: (a[0], a[1]), aliases=["q"])
    reg.register("sort", lambda *a: (a[0], a[1]))
    reg.register("set", lambda *a: (a[0], a[1]))
    reg.register("stats", lambda *a: (a[0], a[1]))
    reg.register("help", lambda *a: (a[0], a[1]), aliases=["h"])
    return reg


class TestCompleterComplete:
    def test_prefix_match(self) -> None:
        c = CommandCompleter(_make_registry())
        state = c.complete("so")
        assert "sort" in state.matches
        assert state.index == 0
        assert state.range_prefix == ""
        assert state.typed_command == "so"

    def test_all_s_commands(self) -> None:
        c = CommandCompleter(_make_registry())
        state = c.complete("s")
        # set, sort, stats all start with s
        assert "set" in state.matches
        assert "sort" in state.matches
        assert "stats" in state.matches

    def test_range_prefix_extraction(self) -> None:
        c = CommandCompleter(_make_registry())
        state = c.complete("%so")
        assert state.range_prefix == "%"
        assert state.typed_command == "so"
        assert "sort" in state.matches

    def test_no_matches(self) -> None:
        c = CommandCompleter(_make_registry())
        state = c.complete("xyz")
        assert state.matches == ()

    def test_empty_input(self) -> None:
        c = CommandCompleter(_make_registry())
        state = c.complete("")
        assert state.matches == ()


class TestCompleterCycling:
    def test_cycle_next(self) -> None:
        state = CompletionState(matches=("a", "b", "c"), index=0)
        new = CommandCompleter.cycle_next(state)
        assert new.index == 1

    def test_cycle_next_wraps(self) -> None:
        state = CompletionState(matches=("a", "b", "c"), index=2)
        new = CommandCompleter.cycle_next(state)
        assert new.index == 0

    def test_cycle_prev(self) -> None:
        state = CompletionState(matches=("a", "b", "c"), index=1)
        new = CommandCompleter.cycle_prev(state)
        assert new.index == 0

    def test_cycle_prev_wraps(self) -> None:
        state = CompletionState(matches=("a", "b", "c"), index=0)
        new = CommandCompleter.cycle_prev(state)
        assert new.index == 2

    def test_cycle_empty_matches(self) -> None:
        state = CompletionState(matches=(), index=0)
        assert CommandCompleter.cycle_next(state) is state
        assert CommandCompleter.cycle_prev(state) is state


class TestCompleterGhostAndAccept:
    def test_current_ghost(self) -> None:
        state = CompletionState(matches=("sort", "set"), index=0, range_prefix="%")
        assert CommandCompleter.current_ghost(state) == "%sort"

    def test_current_ghost_with_cycling(self) -> None:
        state = CompletionState(matches=("sort", "set"), index=1, range_prefix="")
        assert CommandCompleter.current_ghost(state) == "set"

    def test_current_ghost_empty(self) -> None:
        state = CompletionState(matches=(), index=0)
        assert CommandCompleter.current_ghost(state) == ""

    def test_accept(self) -> None:
        state = CompletionState(matches=("sort", "set"), index=0, range_prefix="%")
        assert CommandCompleter.accept(state) == "%sort"

    def test_accept_empty(self) -> None:
        state = CompletionState(matches=(), index=0)
        assert CommandCompleter.accept(state) == ""


class TestCompleterIntegration:
    """End-to-end: complete → cycle → accept."""

    def test_complete_then_tab_cycle(self) -> None:
        c = CommandCompleter(_make_registry())
        state = c.complete("s")
        first = CommandCompleter.current_ghost(state)
        assert first  # some match

        state2 = CommandCompleter.cycle_next(state)
        second = CommandCompleter.current_ghost(state2)
        assert second != first or len(state.matches) == 1

    def test_range_preserved_through_accept(self) -> None:
        c = CommandCompleter(_make_registry())
        state = c.complete("%so")
        accepted = CommandCompleter.accept(state)
        assert accepted.startswith("%")
        assert "sort" in accepted

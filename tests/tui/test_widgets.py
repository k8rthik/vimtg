"""Tests for TUI widgets — StatusLine, CommandLine, SearchResults."""

import pytest

from vimtg.domain.card import Card
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.search_results import SearchResults, _compute_scroll_offset


def _card(
    name: str,
    *,
    cmc: float = 1.0,
    mana_cost: str = "{R}",
    type_line: str = "Instant",
    oracle_text: str = "",
    usd: float | None = 1.5,
) -> Card:
    """Build a minimal Card for widget rendering tests."""
    data = {
        "id": f"id-{name}",
        "name": name,
        "mana_cost": mana_cost,
        "cmc": cmc,
        "type_line": type_line,
        "oracle_text": oracle_text,
        "set": "tst",
        "rarity": "common",
        "prices": {"usd": str(usd) if usd is not None else None},
    }
    return Card.from_scryfall(data)


def test_command_line_show_sets_prefix() -> None:
    cl = CommandLine()
    cl.show(":")
    assert cl.prefix == ":"
    assert cl.text == ""
    assert cl.message == ""


def test_command_line_hide_clears() -> None:
    cl = CommandLine()
    cl.show(":")
    cl.text = "sort"
    cl.hide()
    assert cl.prefix == ""
    assert cl.text == ""


def test_command_line_set_message_clears_prefix() -> None:
    cl = CommandLine()
    cl.show(":")
    cl.set_message("3 cards sorted")
    assert cl.message == "3 cards sorted"
    assert cl.prefix == ""


def test_search_results_select_next_clamps() -> None:
    sr = SearchResults()
    sr.results = []
    sr.select_next()
    assert sr.selected == 0


def test_search_results_select_prev_clamps() -> None:
    sr = SearchResults()
    sr.selected = 0
    sr.select_prev()
    assert sr.selected == 0


def test_search_results_get_selected_empty() -> None:
    sr = SearchResults()
    sr.results = []
    assert sr.get_selected() is None


class TestSearchResultsRender:
    def test_empty_renders_blank(self) -> None:
        sr = SearchResults()
        sr.results = []
        assert sr.render().plain == ""

    def test_single_match_singular_label(self) -> None:
        sr = SearchResults()
        sr.results = [_card("Lightning Bolt")]
        text = sr.render().plain
        assert "1 match " in text
        assert "Lightning Bolt" in text

    def test_multiple_matches_plural_label(self) -> None:
        sr = SearchResults()
        sr.results = [_card("Lightning Bolt"), _card("Lava Spike")]
        assert "2 matches" in sr.render().plain

    def test_selected_shows_indicator_and_oracle(self) -> None:
        sr = SearchResults()
        sr.results = [_card("Lightning Bolt", oracle_text="Deal 3 damage.")]
        sr.selected = 0
        text = sr.render().plain
        assert " > " in text
        assert "Deal 3 damage." in text

    def test_long_oracle_text_truncated(self) -> None:
        sr = SearchResults()
        sr.results = [_card("Wall of Text", oracle_text="x" * 200)]
        sr.selected = 0
        assert "..." in sr.render().plain

    def test_price_hidden_when_disabled(self) -> None:
        sr = SearchResults()
        sr.results = [_card("Lightning Bolt", usd=1.5)]
        sr.show_prices = False
        assert "1.50" not in sr.render().plain

    def test_price_shown_when_enabled(self) -> None:
        sr = SearchResults()
        sr.results = [_card("Lightning Bolt", usd=2.0)]
        sr.show_prices = True
        assert "2.00" in sr.render().plain

    def test_scroll_indicators_for_long_list(self) -> None:
        sr = SearchResults()
        sr.results = [_card(f"Card {i}") for i in range(20)]
        # Select near the bottom so the viewport scrolls.
        for _ in range(15):
            sr.select_next()
        text = sr.render().plain
        assert "more above" in text

    def test_more_below_indicator(self) -> None:
        sr = SearchResults()
        sr.results = [_card(f"Card {i}") for i in range(20)]
        sr.selected = 0
        assert "more below" in sr.render().plain


class TestSearchResultsNavigation:
    def test_select_next_advances(self) -> None:
        sr = SearchResults()
        sr.results = [_card("a"), _card("b"), _card("c")]
        sr.select_next()
        assert sr.selected == 1

    def test_select_next_clamps_at_end(self) -> None:
        sr = SearchResults()
        sr.results = [_card("a"), _card("b")]
        sr.select_next()
        sr.select_next()
        sr.select_next()
        assert sr.selected == 1

    def test_select_prev_returns_to_zero(self) -> None:
        sr = SearchResults()
        sr.results = [_card("a"), _card("b")]
        sr.select_next()
        sr.select_prev()
        assert sr.selected == 0

    def test_get_selected_returns_card(self) -> None:
        sr = SearchResults()
        sr.results = [_card("a"), _card("b")]
        sr.select_next()
        selected = sr.get_selected()
        assert selected is not None
        assert selected.name == "b"

    def test_watch_results_resets_scroll(self) -> None:
        sr = SearchResults()
        sr.results = [_card(f"Card {i}") for i in range(20)]
        for _ in range(15):
            sr.select_next()
        assert sr._scroll_offset > 0
        sr.results = [_card("New")]
        assert sr._scroll_offset == 0


# ── _compute_scroll_offset tests ──────────────────────────────────────


class TestComputeScrollOffset:
    """Unit tests for the pure scroll offset function."""

    def test_no_scrolling_when_all_fit(self) -> None:
        assert _compute_scroll_offset(0, 0, total=5, viewport=10) == 0
        assert _compute_scroll_offset(4, 0, total=5, viewport=10) == 0

    def test_no_scrolling_when_exactly_viewport(self) -> None:
        assert _compute_scroll_offset(9, 0, total=10, viewport=10) == 0

    def test_scroll_down_past_scrolloff(self) -> None:
        # 15 items, viewport=10, scrolloff=2. At selected=7 (pos 7), still fits.
        assert _compute_scroll_offset(7, 0, total=15, viewport=10, scrolloff=2) == 0
        # At selected=8 (pos 8 = viewport-1-scrolloff=7 exceeded), scroll
        assert _compute_scroll_offset(8, 0, total=15, viewport=10, scrolloff=2) == 1

    def test_scroll_up_past_scrolloff(self) -> None:
        # Offset=5, selected=6 (viewport pos 1, below scrolloff=2), scroll up
        assert _compute_scroll_offset(6, 5, total=15, viewport=10, scrolloff=2) == 4

    def test_top_boundary_relaxes_scrolloff(self) -> None:
        # At selected=0, offset must be 0 even though scrolloff=2
        assert _compute_scroll_offset(0, 3, total=15, viewport=10, scrolloff=2) == 0
        assert _compute_scroll_offset(1, 3, total=15, viewport=10, scrolloff=2) == 0

    def test_bottom_boundary_clamps_to_max(self) -> None:
        # 15 items, viewport=10. max_offset=5.
        assert _compute_scroll_offset(14, 0, total=15, viewport=10, scrolloff=2) == 5

    def test_offset_never_negative(self) -> None:
        assert _compute_scroll_offset(0, 0, total=15, viewport=10, scrolloff=2) >= 0

    def test_stable_in_middle(self) -> None:
        # selected=7, offset=3 → pos 4, well within scrolloff. Should stay.
        assert _compute_scroll_offset(7, 3, total=15, viewport=10, scrolloff=2) == 3

    @pytest.mark.parametrize("selected", range(15))
    def test_offset_always_valid(self, selected: int) -> None:
        """Offset must always be in [0, total-viewport] for any selection."""
        offset = _compute_scroll_offset(selected, 0, total=15, viewport=10, scrolloff=2)
        assert 0 <= offset <= 5

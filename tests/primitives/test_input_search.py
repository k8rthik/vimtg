"""Input slice: in-deck search (/ ? n N * #) and K.

Expected values come from docs/keybindings.md (Modes, Navigation). Search
is a case-insensitive regex over card lines only, wraps with vim's
"search hit BOTTOM, continuing at TOP" notice, and `*` / `#` match the
whole card name under the cursor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, Ed, editor
from vimtg.editor.modes import Mode
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.deck_view import DeckView

BOTTOM = "search hit BOTTOM, continuing at TOP"
TOP = "search hit TOP, continuing at BOTTOM"

# Shock and Shock Troops: * on Shock must skip Shock Troops
SHOCK_DECK = (
    "// Deck: Shocks\n// Format: modern\n// Tags:\n\n"
    "DCK:\n"
    "    4 Shock\n"
    "    2 Shock Troops\n"
    "    1 Lightning Bolt\n"
    "\n"
    "SB:\n"
    "    2 Shock\n"
    "    1 Shock Troops\n"
)
# rows: 5 Shock, 6 Shock Troops, 7 Lightning Bolt, 10 SB Shock, 11 SB Shock Troops

BOLT_RULES = "deals 3 damage to any target"


def shown(ed: Ed) -> str:
    """The deck view's rendered text, as the user sees it."""
    return ed.screen.query_one("#deck-view", DeckView).render().plain


def prompt(ed: Ed) -> str:
    return ed.screen.query_one("#command-line", CommandLine).prefix


# ── / ────────────────────────────────────────────────────────────


@pytest.mark.primitive("/")
@pytest.mark.asyncio
async def test_slash_opens_the_search_prompt(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("/")
        assert ed.mode is Mode.SEARCH
        assert prompt(ed) == "/"


@pytest.mark.primitive("/")
@pytest.mark.asyncio
async def test_slash_jumps_forward_to_the_next_matching_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("/bolt<CR>")
        assert ed.row == 12
        assert ed.mode is Mode.NORMAL
        assert ed.text == DECK


@pytest.mark.primitive("/")
@pytest.mark.asyncio
async def test_slash_is_case_insensitive(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("/BOLT<CR>")
        assert ed.row == 12


@pytest.mark.primitive("/")
@pytest.mark.asyncio
async def test_slash_takes_a_regex(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(r"/\b16\b<CR>")
        assert ed.row == 17


@pytest.mark.primitive("/")
@pytest.mark.asyncio
async def test_slash_matches_card_lines_only(tmp_path: Path) -> None:
    # "Burn" is metadata and "Creature" a header: neither is a card line
    async with editor(tmp_path) as ed:
        ed.press("8G /burn<CR>")
        assert ed.row == 7
        ed.press("/creature<CR>")
        assert ed.row == 7
        assert ed.text == DECK


@pytest.mark.primitive("/")
@pytest.mark.asyncio
async def test_slash_wraps_past_the_bottom_with_a_notice(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("18G /goblin<CR>")
        assert ed.row == 7
        assert ed.message == BOTTOM


@pytest.mark.primitive("/")
@pytest.mark.asyncio
async def test_empty_slash_repeats_the_last_pattern(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("/bolt|ice<CR>")
        assert ed.row == 12
        ed.press("/<CR>")
        assert ed.row == 13


@pytest.mark.primitive("/")
@pytest.mark.asyncio
async def test_escape_cancels_the_search_prompt(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G /bolt<Esc>")
        assert ed.mode is Mode.NORMAL
        assert ed.row == 7


# ── ? ────────────────────────────────────────────────────────────


@pytest.mark.primitive("?")
@pytest.mark.asyncio
async def test_question_mark_opens_the_backward_prompt(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("?")
        assert ed.mode is Mode.SEARCH
        assert prompt(ed) == "?"


@pytest.mark.primitive("?")
@pytest.mark.asyncio
async def test_question_mark_searches_backward(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("18G ?goblin|eidolon<CR>")
        assert ed.row == 8


@pytest.mark.primitive("?")
@pytest.mark.asyncio
async def test_question_mark_wraps_past_the_top_with_a_notice(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G ?mountain<CR>")
        assert ed.row == 17
        assert ed.message == TOP


# ── n / N ────────────────────────────────────────────────────────


@pytest.mark.primitive("n")
@pytest.mark.asyncio
async def test_n_repeats_the_search_forward(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G /bolt|ice<CR>")
        assert ed.row == 12
        ed.press("n")
        assert ed.row == 13


@pytest.mark.primitive("n")
@pytest.mark.asyncio
async def test_n_wraps_with_the_bottom_notice(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G /bolt|ice<CR> n n")
        assert ed.row == 12
        assert ed.message == BOTTOM


@pytest.mark.primitive("n")
@pytest.mark.asyncio
async def test_n_with_one_match_comes_back_to_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("/sacred<CR>")
        assert ed.row == 16
        ed.press("n")
        assert ed.row == 16
        assert ed.message == BOTTOM


@pytest.mark.primitive("n")
@pytest.mark.asyncio
async def test_counted_n_skips_matches(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G /bolt|ice|mountain<CR> 2n")
        assert ed.row == 17


@pytest.mark.primitive("n", "?")
@pytest.mark.asyncio
async def test_n_after_question_mark_goes_backward(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("18G ?bolt|ice<CR>")
        assert ed.row == 13
        ed.press("n")
        assert ed.row == 12


@pytest.mark.primitive("N")
@pytest.mark.asyncio
async def test_cap_n_repeats_the_search_backward(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G /bolt|ice<CR> n N")
        assert ed.row == 12


@pytest.mark.primitive("N")
@pytest.mark.asyncio
async def test_cap_n_wraps_with_the_top_notice(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G /bolt|ice<CR> N")
        assert ed.row == 13
        assert ed.message == TOP


@pytest.mark.primitive("N", "?")
@pytest.mark.asyncio
async def test_cap_n_after_question_mark_goes_forward(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("18G ?bolt|ice<CR> N")
        assert ed.row == 12
        assert ed.message == BOTTOM


# ── * / # ────────────────────────────────────────────────────────


@pytest.mark.primitive("*")
@pytest.mark.asyncio
async def test_star_finds_the_next_copy_of_the_whole_name(tmp_path: Path) -> None:
    async with editor(tmp_path, SHOCK_DECK) as ed:
        assert ed.text == SHOCK_DECK
        ed.press("6G *")
        assert ed.row == 10


@pytest.mark.primitive("*")
@pytest.mark.asyncio
async def test_star_wraps_to_the_first_copy(tmp_path: Path) -> None:
    async with editor(tmp_path, SHOCK_DECK) as ed:
        ed.press("11G *")
        assert ed.row == 5
        assert ed.message == BOTTOM


@pytest.mark.primitive("*", "n")
@pytest.mark.asyncio
async def test_n_after_star_repeats_the_card_search(tmp_path: Path) -> None:
    async with editor(tmp_path, SHOCK_DECK) as ed:
        ed.press("6G * n")
        assert ed.row == 5


@pytest.mark.primitive("*")
@pytest.mark.asyncio
async def test_star_on_a_name_with_slashes_matches_it_literally(tmp_path: Path) -> None:
    deck = DECK + "    1 Fire // Ice\n"
    async with editor(tmp_path, deck) as ed:
        ed.press("14G *")
        assert ed.row == 21


@pytest.mark.primitive("#")
@pytest.mark.asyncio
async def test_hash_finds_the_previous_copy_of_the_whole_name(tmp_path: Path) -> None:
    async with editor(tmp_path, SHOCK_DECK) as ed:
        ed.press("11G #")
        assert ed.row == 5


@pytest.mark.primitive("#")
@pytest.mark.asyncio
async def test_hash_wraps_to_the_last_copy(tmp_path: Path) -> None:
    async with editor(tmp_path, SHOCK_DECK) as ed:
        ed.press("6G #")
        assert ed.row == 10
        assert ed.message == TOP


@pytest.mark.primitive("#", "N")
@pytest.mark.asyncio
async def test_cap_n_after_hash_searches_forward(tmp_path: Path) -> None:
    async with editor(tmp_path, SHOCK_DECK) as ed:
        ed.press("11G # N")
        assert ed.row == 10


# ── K ────────────────────────────────────────────────────────────


@pytest.mark.primitive("K")
@pytest.mark.asyncio
async def test_k_hides_details_auto_expand_already_shows(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("13G")
        assert BOLT_RULES in shown(ed)
        ed.press("K")
        assert BOLT_RULES not in shown(ed)
        assert ed.text == DECK


@pytest.mark.primitive("K")
@pytest.mark.asyncio
async def test_k_shows_details_when_auto_expand_is_off(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":set<Space>noautoexpand<CR> 13G")
        assert BOLT_RULES not in shown(ed)
        ed.press("K")
        assert BOLT_RULES in shown(ed)


@pytest.mark.primitive("K")
@pytest.mark.asyncio
async def test_k_lasts_until_the_cursor_moves(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":set<Space>noautoexpand<CR> 13G K j k")
        assert BOLT_RULES not in shown(ed)

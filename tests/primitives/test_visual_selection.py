"""Visual mode: entering, shaping, leaving and reselecting a selection.

The deck is line-oriented, so v and V both select whole lines. A
selection is read back through what an action on it does: y puts the
selected lines in the register in buffer order, d removes them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, editor
from vimtg.editor.modes import Mode
from vimtg.tui.widgets.command_line import CommandLine

pytestmark = pytest.mark.asyncio

ROWS = DECK.splitlines()


def rows(*picked: int) -> tuple[str, ...]:
    """The canonical deck's lines at `picked`, as a register holds them."""
    return tuple(ROWS[r] for r in picked)


def deck_without(*dropped: int) -> str:
    """The canonical deck with the lines at `dropped` deleted."""
    kept = [line for r, line in enumerate(ROWS) if r not in dropped]
    return "\n".join(kept) + "\n"


# -- v and V ---------------------------------------------------------------


@pytest.mark.primitive("v")
async def test_v_enters_visual_mode_without_changing_the_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G v")
        assert ed.mode is Mode.VISUAL
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive("V")
async def test_capital_v_enters_visual_line_mode_without_changing_the_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G V")
        assert ed.mode is Mode.VISUAL_LINE
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive("v", "V", "visual:d")
@pytest.mark.parametrize("key", ["v", "V"])
async def test_v_and_capital_v_both_select_whole_card_lines(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G {key}j d")
        assert ed.text == deck_without(7, 8)


@pytest.mark.primitive("v", "V")
@pytest.mark.parametrize("key", ["v", "V"])
async def test_the_same_visual_key_again_leaves_visual_mode(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G {key}j {key}")
        assert ed.mode is Mode.NORMAL
        assert ed.text == DECK
        assert ed.row == 8


@pytest.mark.primitive("v", "V", "visual:d")
async def test_capital_v_inside_v_switches_kind_and_keeps_the_selection(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G vj V")
        assert ed.mode is Mode.VISUAL_LINE
        ed.press("d")
        assert ed.text == deck_without(7, 8)


@pytest.mark.primitive("v", "V", "visual:y")
async def test_v_inside_capital_v_switches_kind_and_keeps_the_selection(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj v")
        assert ed.mode is Mode.VISUAL
        ed.press("y")
        assert ed.register() == rows(7, 8)


# -- growing and shrinking -----------------------------------------------------


@pytest.mark.primitive("V", "visual:y")
async def test_selection_grows_downward_with_j(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vjj y")
        assert ed.register() == rows(7, 8, 9)


@pytest.mark.primitive("V", "visual:y")
async def test_selection_grows_upward_with_k_and_yanks_in_deck_order(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("10G Vkk y")
        assert ed.register() == rows(7, 8, 9)


@pytest.mark.primitive("V", "visual:y")
async def test_reversing_the_motion_shrinks_the_selection(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vjjk y")
        assert ed.register() == rows(7, 8)


@pytest.mark.primitive("V", "visual:y")
async def test_moving_past_the_anchor_selects_the_other_side(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G Vj kk y")
        assert ed.register() == rows(7, 8)


@pytest.mark.primitive("V", "visual:y")
async def test_selection_spans_a_blank_line_and_a_header(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        # j skips the blank row 10, so one j from Bonecrusher lands on // Instant
        ed.press("10G Vj")
        assert ed.row == 11
        ed.press("y")
        assert ed.register() == rows(9, 10, 11)


@pytest.mark.primitive("V", "visual:y")
async def test_selection_spans_from_the_deck_into_the_sideboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("17G VG y")
        assert ed.register() == rows(16, 17, 18, 19, 20)


# -- o ---------------------------------------------------------------------------


@pytest.mark.primitive("visual:o")
async def test_o_moves_the_cursor_to_the_other_end(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G Vj o")
        assert ed.row == 8
        assert ed.mode is Mode.VISUAL_LINE
        assert ed.text == DECK


@pytest.mark.primitive("visual:o", "visual:y")
async def test_o_keeps_the_same_lines_selected(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G Vj o y")
        assert ed.register() == rows(8, 9)


@pytest.mark.primitive("visual:o", "visual:y")
async def test_after_o_a_motion_grows_the_other_end(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G Vj o k y")
        assert ed.register() == rows(7, 8, 9)


@pytest.mark.primitive("visual:o")
async def test_o_twice_returns_to_the_first_end(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G Vj o o")
        assert ed.row == 9


@pytest.mark.primitive("visual:o", "v")
async def test_o_works_in_charwise_visual_too(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G vj o k y")
        assert ed.register() == rows(7, 8, 9)


# -- escape ----------------------------------------------------------------------


@pytest.mark.primitive("visual:escape")
async def test_escape_returns_to_normal_mode(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vjj <Esc>")
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("visual:escape")
async def test_escape_leaves_the_deck_unchanged(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vjj <Esc>")
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive("visual:escape")
async def test_escape_leaves_the_cursor_where_the_selection_ended(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vjj <Esc>")
        assert ed.row == 9


@pytest.mark.primitive("visual:escape", "v")
async def test_escape_from_charwise_visual_returns_to_normal(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G vj <Esc>")
        assert ed.mode is Mode.NORMAL
        assert ed.text == DECK


@pytest.mark.primitive("visual:escape")
async def test_after_escape_dd_deletes_only_the_cursor_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vjj <Esc> dd")
        assert ed.text == deck_without(9)


# -- gv ----------------------------------------------------------------------------


@pytest.mark.primitive("gv", "visual:escape")
async def test_gv_reselects_after_escape_in_the_same_mode(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj <Esc> G gv")
        assert ed.mode is Mode.VISUAL_LINE
        assert ed.row == 8


@pytest.mark.primitive("gv", "visual:escape", "visual:d")
async def test_gv_after_escape_selects_the_same_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj <Esc> G gv d")
        assert ed.text == deck_without(7, 8)


@pytest.mark.primitive("gv", "v")
async def test_gv_restores_charwise_visual(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G vj <Esc> G gv")
        assert ed.mode is Mode.VISUAL


@pytest.mark.primitive("gv")
async def test_gv_puts_the_cursor_at_the_same_end(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G Vk <Esc> G gv")
        assert ed.row == 7


@pytest.mark.primitive("gv", "visual:y", "visual:d")
async def test_gv_reselects_after_an_action(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj y 17G gv d")
        assert ed.text == deck_without(7, 8)


@pytest.mark.primitive("gv", "visual:y")
async def test_gv_in_visual_mode_swaps_to_the_previous_selection(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj <Esc> 13G V gv y")
        assert ed.register() == rows(7, 8)


@pytest.mark.primitive("gv", "visual:y")
async def test_gv_twice_in_visual_mode_swaps_back(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj <Esc> 13G V gv gv y")
        assert ed.register() == rows(12)


@pytest.mark.primitive("gv")
async def test_gv_with_no_previous_selection_stays_in_normal_mode(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G gv")
        assert ed.mode is Mode.NORMAL
        assert ed.text == DECK
        assert ed.row == 7


# -- :'<,'> ------------------------------------------------------------------------


@pytest.mark.primitive("V")
async def test_colon_in_visual_mode_pretypes_the_selection_range(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj :")
        assert ed.mode is Mode.COMMAND
        assert ed.screen.query_one("#command-line", CommandLine).text == "'<,'>"


@pytest.mark.primitive("V")
async def test_escape_from_the_pretyped_range_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj : <Esc>")
        assert ed.mode is Mode.NORMAL
        assert ed.text == DECK


@pytest.mark.primitive("V")
async def test_colon_in_visual_mode_runs_the_command_on_the_selection(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        # Bonecrusher matches /e/ too but sits outside the selection
        ed.press("8G Vj :g/e/d<CR>")
        assert ed.text == deck_without(7, 8)
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("V")
async def test_colon_range_only_touches_matching_lines_in_the_selection(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vjj :g/guide/d<CR>")
        assert ed.text == deck_without(7)


@pytest.mark.primitive("V")
async def test_colon_range_substitutes_only_inside_the_selection(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj :s/i/!/<CR>")
        expected = list(ROWS)
        expected[7] = "    4 Gobl!n Guide"
        expected[8] = "    2 E!dolon of the Great Revel"
        assert ed.lines == expected


@pytest.mark.primitive("V", "visual:escape")
async def test_marks_from_an_escaped_selection_address_an_ex_range(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj <Esc> G")
        ed.ex("'<,'>g/e/d")
        assert ed.text == deck_without(7, 8)


@pytest.mark.primitive("V")
async def test_colon_range_command_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj :g/e/d<CR> u")
        assert ed.text == DECK


@pytest.mark.primitive("visual:escape")
async def test_escape_drops_a_count_typed_in_visual_mode(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj 3 <Esc> +")
        assert ed.lines[8] == "    3 Eidolon of the Great Revel"


@pytest.mark.primitive("visual:escape")
async def test_escape_drops_a_register_typed_in_visual_mode(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G Vj "a <Esc> yy')
        assert ed.register("a") == ()
        assert ed.register() == rows(8)


@pytest.mark.primitive("gv", "visual:o")
async def test_gv_remembers_the_end_o_moved_the_cursor_to(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj o <Esc> G gv")
        assert ed.row == 7

"""Marks, :marks, and the view keys (zz zt zb, Ctrl-D/U, H M L).

Expected values come from docs/keybindings.md and docs/commands.md and,
where they are silent, from vim with its scrolloff margin. The view
cases run a 100-line deck in a 12-row terminal with auto_expand off, so
every buffer line is one screen row and the visible window can be read
off the rendered deck view.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from textual.pilot import Pilot

from tests.primitives.harness import DECK, Ed, editor
from tests.primitives.test_navigation import (
    BOLT,
    EIDOLON,
    FIRE_ICE,
    FOUNDRY,
    GOBLIN,
    LAST,
    RIP,
    SB_ROW,
    goto,
    tall_deck,
    unchanged,
)
from vimtg.config.paths import config_dir
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.deck_view import DeckView

pytestmark = pytest.mark.asyncio

# vim's scrolloff: the rows of context the view keeps around the cursor.
# H / M / L stay inside it so the view does not move (keybindings.md).
SCROLLOFF = 3
SMALL = (100, 12)
TALL = tall_deck(100)
_FILLER = re.compile(r"Filler (\d{3})")


# ── helpers (not in the harness) ─────────────────────────────────────


def no_auto_expand() -> None:
    """One screen row per buffer line: no card details under the cursor."""
    (config_dir() / "config.toml").write_text("[editor]\nauto_expand = false\n", encoding="utf-8")


async def settle(ed: Ed) -> None:
    """Let the app render, as it does between two real keypresses."""
    await Pilot(ed.app).pause()


async def press(ed: Ed, keys: str) -> None:
    """Press each space-separated chunk, rendering after each one."""
    for chunk in keys.split():
        ed.press(chunk)
        await settle(ed)


def view_height(ed: Ed) -> int:
    return int(ed.screen.query_one("#deck-view", DeckView).size.height)


def visible_rows(ed: Ed) -> list[int]:
    """The buffer rows the deck view shows, top to bottom, read from
    the rendered filler names of TALL (row r shows 'Filler {r - 4}')."""
    shown = ed.screen.query_one("#deck-view", DeckView).render().plain.splitlines()
    for i, text in enumerate(shown):
        match = _FILLER.search(text)
        if match:
            top = int(match.group(1)) + 4 - i
            return list(range(top, top + len(shown)))
    raise AssertionError("no filler line is visible")


# ── zz / zt / zb ─────────────────────────────────────────────────────


@pytest.mark.primitive("zz")
async def test_zz_puts_the_cursor_line_in_the_middle_of_the_view(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zz")
        shown = visible_rows(ed)
        assert len(shown) == view_height(ed)
        assert shown.index(50) in ((len(shown) - 1) // 2, len(shown) // 2)
        assert ed.row == 50
        unchanged(ed, TALL)


@pytest.mark.primitive("zt")
async def test_zt_puts_the_cursor_line_at_the_top_inside_scrolloff(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zt")
        assert visible_rows(ed)[0] == 50 - SCROLLOFF
        assert ed.row == 50
        unchanged(ed, TALL)


@pytest.mark.primitive("zb")
async def test_zb_puts_the_cursor_line_at_the_bottom_inside_scrolloff(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zt zb")
        assert visible_rows(ed)[-1] == 50 + SCROLLOFF
        assert ed.row == 50
        unchanged(ed, TALL)


@pytest.mark.primitive("zt")
async def test_the_view_zt_set_stays_while_the_cursor_moves_inside_it(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zt")
        before = visible_rows(ed)
        await press(ed, "j j")
        assert ed.row == 52
        assert visible_rows(ed) == before
        unchanged(ed, TALL)


@pytest.mark.primitive("zt")
async def test_zt_near_the_top_cannot_scroll_above_the_first_line(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G 3G zt")
        assert visible_rows(ed)[0] == 0
        assert ed.row == 2
        unchanged(ed, TALL)


@pytest.mark.primitive("zb")
async def test_zb_near_the_top_cannot_scroll_above_the_first_line(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "6G zb")
        assert visible_rows(ed)[0] == 0
        assert ed.row == 5
        unchanged(ed, TALL)


@pytest.mark.parametrize("key", ["zz", "zt", "zb"])
@pytest.mark.primitive("zz", "zt", "zb")
async def test_scroll_keys_leave_a_deck_that_fits_unscrolled(tmp_path: Path, key: str) -> None:
    no_auto_expand()
    async with editor(tmp_path) as ed:
        await press(ed, f"G {key}")
        shown = ed.screen.query_one("#deck-view", DeckView).render().plain.splitlines()
        assert "// Deck: Burn" in shown[0]
        assert "Rest in Peace" in shown[LAST]
        assert ed.row == LAST
        unchanged(ed)


@pytest.mark.parametrize("key", ["zz", "zt", "zb"])
@pytest.mark.primitive("zz", "zt", "zb")
async def test_scroll_keys_work_with_card_details_expanded(tmp_path: Path, key: str) -> None:
    """With auto_expand on (the default) the cursor card shows its
    details; scrolling still never moves the cursor or edits."""
    async with editor(tmp_path, size=SMALL) as ed:
        await press(ed, f"13G {key}")
        assert ed.row == BOLT
        unchanged(ed)


# ── Ctrl-D / Ctrl-U ──────────────────────────────────────────────────


@pytest.mark.primitive("ctrl_d")
@pytest.mark.xfail(strict=True, reason=(
    "BUG: Ctrl-D should move half the visible view (11 rows -> 5 lines, 50 -> 55); "
    "it always moves 15 lines (50 -> 65)"
))
async def test_ctrl_d_moves_the_cursor_down_half_the_view(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zz <C-d>")
        assert ed.row == 50 + view_height(ed) // 2
        unchanged(ed, TALL)


@pytest.mark.primitive("ctrl_d")
@pytest.mark.xfail(strict=True, reason=(
    "BUG: Ctrl-D should scroll the view with the cursor, keeping its screen line "
    "(6th of 11); the cursor jumps 15 lines and the view only follows it to the margin"
))
async def test_ctrl_d_scrolls_the_view_with_the_cursor(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zz")
        screen_line = visible_rows(ed).index(ed.row)
        await press(ed, "<C-d>")
        assert visible_rows(ed).index(ed.row) == screen_line
        unchanged(ed, TALL)


@pytest.mark.primitive("ctrl_d")
async def test_ctrl_d_moves_down_and_keeps_the_cursor_visible(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G <C-d>")
        assert ed.row > 50
        assert ed.row in visible_rows(ed)
        unchanged(ed, TALL)


@pytest.mark.primitive("ctrl_d")
async def test_ctrl_d_near_the_end_stops_on_the_last_line(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "97G <C-d>")
        assert ed.row == 99
        await press(ed, "<C-d>")
        assert ed.row == 99
        unchanged(ed, TALL)


@pytest.mark.primitive("ctrl_u")
@pytest.mark.xfail(strict=True, reason=(
    "BUG: Ctrl-U should move half the visible view (11 rows -> 5 lines, 50 -> 45); "
    "it always moves 15 lines (50 -> 35)"
))
async def test_ctrl_u_moves_the_cursor_up_half_the_view(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zz <C-u>")
        assert ed.row == 50 - view_height(ed) // 2
        unchanged(ed, TALL)


@pytest.mark.primitive("ctrl_u")
async def test_ctrl_u_moves_up_and_keeps_the_cursor_visible(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G <C-u>")
        assert ed.row < 50
        assert ed.row in visible_rows(ed)
        unchanged(ed, TALL)


@pytest.mark.primitive("ctrl_u")
async def test_ctrl_u_near_the_top_stops_on_the_first_line(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "4j <C-u>")
        assert ed.row == 0
        await press(ed, "<C-u>")
        assert ed.row == 0
        unchanged(ed, TALL)


@pytest.mark.primitive("ctrl_d", "ctrl_u")
async def test_half_pages_on_the_canonical_deck_reach_both_ends(tmp_path: Path) -> None:
    async with editor(tmp_path, size=SMALL) as ed:
        await press(ed, "<C-d> <C-d> <C-d>")
        assert ed.row == LAST
        await press(ed, "<C-u> <C-u> <C-u>")
        assert ed.row == 0
        unchanged(ed)


# ── H / M / L ────────────────────────────────────────────────────────
# "51G zz" leaves rows 45-55 on screen with the cursor on 50; j / k
# inside that window do not scroll it.


@pytest.mark.primitive("H")
async def test_big_h_goes_to_the_top_of_the_view_inside_scrolloff(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zz 2j")
        before = visible_rows(ed)
        await press(ed, "H")
        assert ed.row == before[0] + SCROLLOFF
        assert visible_rows(ed) == before
        unchanged(ed, TALL)


@pytest.mark.primitive("M")
async def test_big_m_goes_to_the_middle_of_the_view(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zz 2j")
        before = visible_rows(ed)
        await press(ed, "M")
        assert ed.row == before[len(before) // 2]
        assert visible_rows(ed) == before
        unchanged(ed, TALL)


@pytest.mark.primitive("L")
async def test_big_l_goes_to_the_bottom_of_the_view_inside_scrolloff(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zz 2k")
        before = visible_rows(ed)
        await press(ed, "L")
        assert ed.row == before[-1] - SCROLLOFF
        assert visible_rows(ed) == before
        unchanged(ed, TALL)


@pytest.mark.primitive("H")
async def test_big_h_at_the_top_of_the_deck_goes_to_the_first_line(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "5j")
        assert ed.row == 6
        await press(ed, "H")
        assert ed.row == 0
        unchanged(ed, TALL)


@pytest.mark.primitive("L")
async def test_big_l_at_the_end_of_the_deck_goes_to_the_last_line(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "G 3k")
        assert ed.row == 96
        await press(ed, "L")
        assert ed.row == 99
        unchanged(ed, TALL)


@pytest.mark.primitive("H")
async def test_count_big_h_at_the_top_of_the_deck_is_that_visible_line(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "5j 3H")
        assert ed.row == 2  # the third visible line, // Tags:
        unchanged(ed, TALL)


@pytest.mark.primitive("H")
async def test_count_big_h_on_a_scrolled_view_is_that_visible_line(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zz 2j")
        before = visible_rows(ed)
        await press(ed, "5H")
        assert ed.row == before[4]
        unchanged(ed, TALL)


@pytest.mark.primitive("L")
async def test_count_big_l_on_a_scrolled_view_is_that_line_from_the_bottom(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zz 2j")
        before = visible_rows(ed)
        await press(ed, "5L")
        assert ed.row == before[-5]
        unchanged(ed, TALL)


@pytest.mark.primitive("H", "L")
async def test_counts_larger_than_the_view_stop_inside_scrolloff(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "51G zz")
        before = visible_rows(ed)
        await press(ed, "50H")
        assert ed.row == before[-1] - SCROLLOFF
        await press(ed, "50L")
        assert ed.row == before[0] + SCROLLOFF
        assert visible_rows(ed) == before
        unchanged(ed, TALL)


@pytest.mark.primitive("M")
async def test_big_m_at_the_top_of_the_deck_goes_to_the_middle_visible_line(tmp_path: Path) -> None:
    no_auto_expand()
    async with editor(tmp_path, TALL, size=SMALL) as ed:
        await press(ed, "5j")
        shown = visible_rows(ed)
        assert shown[0] == 0
        await press(ed, "M")
        assert ed.row == shown[len(shown) // 2]
        unchanged(ed, TALL)


@pytest.mark.primitive("H", "M", "L")
async def test_big_h_big_m_big_l_on_a_deck_that_fits_span_the_whole_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await press(ed, "13G H")
        assert ed.row == 0
        await press(ed, "L")
        assert ed.row == LAST
        await press(ed, "M")
        assert 0 < ed.row < LAST
        unchanged(ed)


# ── m{a-z} / '{a-z} ──────────────────────────────────────────────────


@pytest.mark.parametrize("letter", ["a", "m", "z"])
@pytest.mark.primitive("m{a-z}", "'{a-z}")
async def test_a_mark_brings_the_cursor_back_to_its_card(tmp_path: Path, letter: str) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, BOLT)
        ed.press(f"m{letter}")
        assert ed.row == BOLT  # setting a mark does not move
        ed.press(f"G '{letter}")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("m{a-z}", "'{a-z}")
async def test_two_marks_are_independent(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("ma")
        ed.press("gg")
        goto(ed, FOUNDRY)
        ed.press("mb gg 'a")
        assert ed.row == GOBLIN
        ed.press("'b")
        assert ed.row == FOUNDRY
        unchanged(ed)


@pytest.mark.primitive("m{a-z}")
async def test_setting_a_mark_again_moves_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("ma 4j ma gg 'a")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.parametrize("row", [0, SB_ROW, RIP])
@pytest.mark.primitive("m{a-z}", "'{a-z}")
async def test_marks_work_on_metadata_the_sb_marker_and_the_sideboard(
    tmp_path: Path, row: int,
) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, row)
        ed.press("mk")
        ed.press("gg 13G 'k")
        assert ed.row == row
        unchanged(ed)


@pytest.mark.primitive("m{a-z}", "'{a-z}")
async def test_a_mark_on_a_hundred_line_deck(tmp_path: Path) -> None:
    async with editor(tmp_path, TALL) as ed:
        ed.press("90G mq gg 'q")
        assert ed.row == 89
        assert ed.line == "1 Filler 085"
        unchanged(ed, TALL)


@pytest.mark.primitive("'{a-z}")
async def test_a_mark_follows_its_card_when_a_line_is_deleted_above(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FOUNDRY)
        ed.press("ma")
        ed.press("9G")
        assert ed.row == EIDOLON
        ed.press("dd")
        assert "2 Eidolon of the Great Revel" not in ed.cards
        ed.press("gg 'a")
        assert ed.line == "4 Sacred Foundry"


@pytest.mark.primitive("'{a-z}")
async def test_a_mark_follows_its_card_when_a_line_is_put_above(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FOUNDRY)
        ed.press("ma 8G yy P")
        assert len(ed.lines) == len(DECK.splitlines()) + 1
        ed.press("gg 'a")
        assert ed.line == "4 Sacred Foundry"


@pytest.mark.primitive("'{a-z}")
async def test_a_mark_follows_its_card_through_a_zone_move_above(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FOUNDRY)
        ed.press("ma 9G zs")
        ed.press("gg 'a")
        assert ed.line == "4 Sacred Foundry"


@pytest.mark.primitive("'{a-z}")
async def test_a_mark_stays_when_a_line_below_it_is_deleted(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("ma 17G dd gg 'a")
        assert ed.row == GOBLIN
        assert ed.line == "4 Goblin Guide"


@pytest.mark.primitive("'{a-z}")
async def test_a_mark_on_a_deleted_line_is_gone(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FIRE_ICE)
        ed.press("ma dd gg")
        ed.press("'a")
        assert ed.row == 0
        assert "not set" in ed.message.lower()


@pytest.mark.primitive("'{a-z}")
async def test_jumping_to_an_unset_mark_does_not_move(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, BOLT)
        ed.press("'q")
        assert ed.row == BOLT
        assert "not set" in ed.message.lower()
        unchanged(ed)


@pytest.mark.primitive("'{a-z}")
@pytest.mark.xfail(strict=True, reason=(
    "BUG: 'q on an unset mark should be an error (vim's E20, as '' already is); "
    "it shows a plain message \"Mark 'q' not set\""
))
async def test_jumping_to_an_unset_mark_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("'q")
        assert ed.is_error


# ── :marks ───────────────────────────────────────────────────────────


@pytest.mark.primitive(":marks")
async def test_marks_with_none_set_says_so(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":marks<CR>")
        assert "no marks" in ed.message.lower()
        unchanged(ed)


@pytest.mark.primitive(":marks", "m{a-z}")
async def test_marks_lists_each_mark_with_its_line_number_and_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FOUNDRY)
        ed.press("mb")
        ed.press("gg")
        goto(ed, EIDOLON)
        ed.press("ma")
        ed.press(":marks<CR>")
        assert re.search(
            r"\ba\b\D*\b9\b.*Eidolon of the Great Revel.*\bb\b\D*\b17\b.*Sacred Foundry",
            ed.message,
        ), ed.message
        assert ed.row == EIDOLON
        unchanged(ed)


@pytest.mark.primitive(":marks")
async def test_marks_shows_the_shifted_line_after_a_delete_above(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FOUNDRY)
        ed.press("ma 9G dd :marks<CR>")
        assert re.search(r"\ba\b\D*\b16\b.*Sacred Foundry", ed.message), ed.message


@pytest.mark.primitive(":marks")
async def test_marks_too_long_for_one_line_opens_a_pager_with_every_mark(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, TALL) as ed:
        for i, letter in enumerate("abcdefghijklmnopqrstuvwxyz"):
            ed.press(f"{10 + i}G m{letter}")
        ed.press(":marks<CR>")
        await settle(ed)
        pager = ed.app.screen
        assert not isinstance(pager, MainScreen)
        body = "\n".join(
            str(w.render()) for w in pager.query("#help-body")
        )
        for i, letter in enumerate("abcdefghijklmnopqrstuvwxyz"):
            assert re.search(rf"\b{letter}\b\D*\b{10 + i}\b.*Filler {5 + i:03d}", body), letter
        main = next(s for s in ed.app.screen_stack if isinstance(s, MainScreen))
        assert main._state.buffer.to_text() == TALL
        assert main._state.modified is False

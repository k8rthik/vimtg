"""The jumplist (Ctrl-O, Tab as Ctrl-I, ''), and every motion on a deck
with no cards and on a 100-line deck, driven through real keys.

Expected rows come from docs/keybindings.md (the jumplist rules) and,
where it is silent, from vim. Row names refer to the canonical DECK map
in the harness.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import editor
from tests.primitives.test_navigation import (
    BOLT,
    DCK_ROW,
    EMPTY_DECK,
    FOUNDRY,
    GOBLIN,
    INSTANT_HDR,
    LAND_HDR,
    LAST,
    MOUNTAIN,
    goto,
    tall_deck,
    unchanged,
)

pytestmark = pytest.mark.asyncio

# ── the jumplist: Ctrl-O, Tab (Ctrl-I), '' ──────────────────────────

# (keys, the row they land on from Bolt) for every documented jump
# reachable from the canonical deck at full size, where the whole deck
# is visible so H / M / L target its first, middle and last lines.
JUMPS = {
    "gg": ("gg", 0),
    "G": ("G", LAST),
    "{n}G": ("5G", DCK_ROW),
    "{": ("{", None),
    "}": ("}", None),
    "[[": ("[[", INSTANT_HDR),
    "]]": ("]]", LAND_HDR),
    "H": ("H", 0),
    "M": ("M", None),
    "L": ("L", LAST),
}


@pytest.mark.parametrize("name", list(JUMPS))
@pytest.mark.primitive("ctrl_o", "gg", "G", "{", "}", "[[", "]]", "H", "M", "L")
async def test_ctrl_o_returns_from_each_jump_motion(tmp_path: Path, name: str) -> None:
    keys, lands = JUMPS[name]
    async with editor(tmp_path) as ed:
        goto(ed, BOLT)
        ed.press(keys)
        assert ed.row != BOLT
        if lands is not None:
            assert ed.row == lands
        ed.press("<C-o>")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("ctrl_o", "'{a-z}")
async def test_ctrl_o_returns_from_a_mark_jump(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("ma")
        goto(ed, BOLT)
        ed.press("'a")
        assert ed.row == 0
        ed.press("<C-o>")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("ctrl_o", "''")
async def test_ctrl_o_returns_from_a_quote_quote_jump(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G 2k")  # jump 0 -> 20, then walk to Mountain
        assert ed.row == MOUNTAIN
        ed.press("''")
        assert ed.row == 0
        ed.press("<C-o>")
        assert ed.row == MOUNTAIN
        unchanged(ed)


@pytest.mark.parametrize("keys", ["j", "k", "w", "b", "<C-d>", "<C-u>"])
@pytest.mark.primitive("ctrl_o", "j", "k", "w", "b", "ctrl_d", "ctrl_u")
async def test_plain_motions_are_not_jumps(tmp_path: Path, keys: str) -> None:
    """After 1 -> 17G, a plain motion adds no entry: Ctrl-O goes back
    past it to line 1, where the 17G jump started."""
    async with editor(tmp_path) as ed:
        ed.press("17G")
        assert ed.row == FOUNDRY
        ed.press(keys)
        assert ed.row != FOUNDRY
        ed.press("<C-o>")
        assert ed.row == 0
        unchanged(ed)


@pytest.mark.primitive("ctrl_o")
async def test_ctrl_o_walks_back_through_several_jumps(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 13G G")
        ed.press("<C-o>")
        assert ed.row == BOLT
        ed.press("<C-o>")
        assert ed.row == GOBLIN
        ed.press("<C-o>")
        assert ed.row == 0
        unchanged(ed)


@pytest.mark.primitive("ctrl_o")
async def test_ctrl_o_past_the_oldest_jump_stays(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G <C-o> <C-o> <C-o>")
        assert ed.row == 0
        unchanged(ed)


@pytest.mark.primitive("ctrl_o")
async def test_ctrl_o_with_no_jumps_stays(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, BOLT)
        ed.press("<C-o>")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("ctrl_o")
async def test_count_ctrl_o_goes_back_that_many_jumps(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 13G G 2<C-o>")
        assert ed.row == GOBLIN
        unchanged(ed)


@pytest.mark.primitive("ctrl_o")
async def test_jumplist_rows_do_not_follow_later_edits(tmp_path: Path) -> None:
    """keybindings.md: "rows do not follow later edits"."""
    async with editor(tmp_path) as ed:
        goto(ed, FOUNDRY)
        ed.press("gg")
        ed.press("6j")
        assert ed.line == "2 Eidolon of the Great Revel"
        ed.press("dd")
        ed.press("<C-o>")
        assert ed.row == FOUNDRY


@pytest.mark.primitive("ctrl_o")
async def test_a_zone_move_far_away_is_a_jump(tmp_path: Path) -> None:
    """keybindings.md lists a zone move that files the card more than a
    line away (zs) among the jumps."""
    async with editor(tmp_path) as ed:
        goto(ed, BOLT)
        ed.press("zs")
        assert ed.line.endswith("Lightning Bolt")
        assert any(line.strip() == "SB:" for line in ed.lines[: ed.row])
        ed.press("<C-o>")
        assert ed.row == BOLT


@pytest.mark.primitive("ctrl_o")
async def test_jumplist_keeps_the_newest_hundred_places(tmp_path: Path) -> None:
    text = tall_deck(110)
    async with editor(tmp_path, text) as ed:
        for n in range(2, 107):  # 105 jumps, leaving rows 0..104
            ed.press(f"{n}G")
        visited = set()
        for _ in range(120):
            ed.press("<C-o>")
            visited.add(ed.row)
        assert visited.isdisjoint(range(5)), "the five oldest places are forgotten"
        assert 10 in visited
        unchanged(ed, text)


@pytest.mark.primitive("tab")
async def test_tab_walks_forward_after_ctrl_o(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G G <C-o> <C-o>")
        assert ed.row == 0
        ed.press("<Tab>")
        assert ed.row == GOBLIN
        ed.press("<Tab>")
        assert ed.row == LAST
        unchanged(ed)


@pytest.mark.primitive("tab")
async def test_tab_at_the_newest_place_stays(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G G <C-o> <Tab> <Tab> <Tab>")
        assert ed.row == LAST
        unchanged(ed)


@pytest.mark.primitive("tab")
async def test_tab_without_walking_back_stays(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G G")
        ed.press("<Tab>")
        assert ed.row == LAST
        unchanged(ed)


@pytest.mark.primitive("tab")
async def test_count_tab_goes_forward_that_many_places(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 13G G 3<C-o>")
        assert ed.row == 0
        ed.press("2<Tab>")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("''")
async def test_quote_quote_returns_to_where_the_latest_jump_left(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, BOLT)
        ed.press("G")
        ed.press("''")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("''")
async def test_quote_quote_again_comes_back(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, BOLT)
        ed.press("G '' ''")
        assert ed.row == LAST
        ed.press("''")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("''")
async def test_quote_quote_ignores_plain_motions_since_the_jump(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, BOLT)
        ed.press("G 3k b")
        ed.press("''")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("''")
async def test_quote_quote_follows_the_latest_of_several_jumps(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 13G ''")
        assert ed.row == GOBLIN
        unchanged(ed)


@pytest.mark.primitive("''")
async def test_quote_quote_with_no_jump_does_not_move(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, BOLT)
        ed.press("''")
        assert ed.row == BOLT
        unchanged(ed)


# ── a deck with no cards, and a 100-line deck ───────────────────────

ALL_MOTION_KEYS = [
    "j", "k", "gg", "G", "3G", "w", "b", "{", "}", "[[", "]]", "H", "M", "L",
    "<C-d>", "<C-u>", "<C-o>", "<Tab>", "''", "zz", "zt", "zb",
]


@pytest.mark.parametrize("keys", ALL_MOTION_KEYS)
@pytest.mark.primitive(
    "j", "k", "gg", "G", "w", "b", "{", "}", "[[", "]]", "H", "M", "L",
    "ctrl_d", "ctrl_u", "ctrl_o", "tab", "''", "zz", "zt", "zb",
)
async def test_every_motion_on_a_deck_with_no_cards_keeps_it_unedited(
    tmp_path: Path, keys: str,
) -> None:
    async with editor(tmp_path, EMPTY_DECK) as ed:
        opened = ed.text
        ed.press("3G")
        ed.press(keys)
        assert 0 <= ed.row < len(ed.lines)
        unchanged(ed, opened)


@pytest.mark.primitive("w", "b")
async def test_w_and_b_on_a_deck_with_no_cards_stay_put(tmp_path: Path) -> None:
    async with editor(tmp_path, EMPTY_DECK) as ed:
        opened = ed.text
        ed.press("2G w")
        assert ed.row == 1
        ed.press("b")
        assert ed.row == 1
        unchanged(ed, opened)


@pytest.mark.primitive("G", "gg")
async def test_big_g_and_gg_on_a_deck_with_no_cards(tmp_path: Path) -> None:
    async with editor(tmp_path, EMPTY_DECK) as ed:
        opened = ed.text
        ed.press("G")
        assert ed.line == "DCK:"
        assert ed.row == len(ed.lines) - 1
        ed.press("gg")
        assert ed.row == 0
        unchanged(ed, opened)


@pytest.mark.primitive("G", "gg", "j", "k")
async def test_line_motions_on_a_hundred_line_deck(tmp_path: Path) -> None:
    text = tall_deck(100)
    async with editor(tmp_path, text) as ed:
        assert len(ed.lines) == 100
        ed.press("G")
        assert ed.row == 99
        assert ed.line == "1 Filler 095"
        ed.press("50G")
        assert ed.row == 49
        assert ed.line == "1 Filler 045"
        ed.press("10j")
        assert ed.row == 59
        ed.press("200k")
        assert ed.row == 0
        ed.press("500j")
        assert ed.row == 99
        ed.press("75gg")
        assert ed.row == 74
        unchanged(ed, text)


@pytest.mark.primitive("w", "b", "}")
async def test_card_motions_on_a_hundred_line_deck(tmp_path: Path) -> None:
    text = tall_deck(100)
    async with editor(tmp_path, text) as ed:
        ed.press("w")
        assert ed.line == "1 Filler 001"
        ed.press("40w")
        assert ed.line == "1 Filler 041"
        ed.press("15b")
        assert ed.line == "1 Filler 026"
        ed.press("}")  # the deck is one section: past it is the end
        assert ed.row == 99
        unchanged(ed, text)

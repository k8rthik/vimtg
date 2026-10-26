"""Visual mode: the line operators d y c x S C D Y and the puts p P.

Most cases select Goblin Guide and Eidolon (rows 7-8) with "8G Vj".
Per docs/keybindings.md each action ends the selection and is one undo
step.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.pilot import Pilot

from tests.conftest import FakeClipboard
from tests.primitives.harness import DECK, Ed, editor
from vimtg.editor.modes import Mode

pytestmark = pytest.mark.asyncio

ROWS = DECK.splitlines()
GOBLIN, EIDOLON = ROWS[7], ROWS[8]
BOLT, FIRE_ICE = ROWS[12], ROWS[13]


async def settle(ed: Ed) -> None:
    """Let the card search worker deliver its results. Ed.press is
    synchronous, so a search typed through it has not answered yet."""
    await ed.app.workers.wait_for_complete()
    await Pilot(ed.app).pause()


def deck_without(*dropped: int) -> str:
    kept = [line for r, line in enumerate(ROWS) if r not in dropped]
    return "\n".join(kept) + "\n"


def deck_replacing(start: int, end: int, new: list[str]) -> str:
    """The canonical deck with rows start..end (inclusive) replaced by `new`."""
    return "\n".join([*ROWS[:start], *new, *ROWS[end + 1:]]) + "\n"


DELETERS = [
    pytest.param("d", marks=pytest.mark.primitive("visual:d"), id="d"),
    pytest.param("x", marks=pytest.mark.primitive("visual:x"), id="x"),
    pytest.param("D", marks=pytest.mark.primitive("visual:D"), id="D"),
]
YANKERS = [
    pytest.param("y", marks=pytest.mark.primitive("visual:y"), id="y"),
    pytest.param("Y", marks=pytest.mark.primitive("visual:Y"), id="Y"),
]
CHANGERS = [
    pytest.param("c", marks=pytest.mark.primitive("visual:c"), id="c"),
    pytest.param("S", marks=pytest.mark.primitive("visual:S"), id="S"),
    pytest.param("C", marks=pytest.mark.primitive("visual:C"), id="C"),
]


# -- d x D -----------------------------------------------------------------------


@pytest.mark.parametrize("key", DELETERS)
async def test_delete_removes_the_selected_lines(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key}")
        assert ed.text == deck_without(7, 8)
        assert ed.modified is True


@pytest.mark.parametrize("key", DELETERS)
async def test_delete_puts_the_lines_in_the_unnamed_register(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key}")
        assert ed.register() == (GOBLIN, EIDOLON)


@pytest.mark.parametrize("key", DELETERS)
async def test_delete_leaves_the_cursor_on_the_line_that_followed(
    tmp_path: Path, key: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key}")
        assert ed.row == 7
        assert ed.line == "3 Bonecrusher Giant // Stomp"


@pytest.mark.parametrize("key", DELETERS)
async def test_delete_returns_to_normal_mode(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key}")
        assert ed.mode is Mode.NORMAL


@pytest.mark.parametrize("key", DELETERS)
async def test_delete_undoes_in_one_step(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key} u")
        assert ed.text == DECK


@pytest.mark.primitive("visual:d")
async def test_delete_across_two_sections_takes_the_header_between(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        # Bonecrusher, the blank, // Instant and Lightning Bolt
        ed.press("10G Vjj d")
        assert ed.text == deck_without(9, 10, 11, 12)


@pytest.mark.primitive("visual:d")
async def test_delete_from_the_deck_into_the_sideboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("17G VG d")
        assert ed.cards == [
            "4 Goblin Guide", "2 Eidolon of the Great Revel",
            "3 Bonecrusher Giant // Stomp", "4 Lightning Bolt", "1 Fire // Ice",
        ]
        assert "SB:" not in ed.lines
        assert ed.register() == tuple(ROWS[16:21])


@pytest.mark.primitive("visual:d")
async def test_delete_from_the_deck_into_the_sideboard_undoes_in_one_step(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press("17G VG d u")
        assert ed.text == DECK


@pytest.mark.primitive("visual:d")
async def test_delete_into_a_named_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G Vj "ad')
        assert ed.register("a") == (GOBLIN, EIDOLON)


@pytest.mark.primitive("visual:d")
async def test_black_hole_delete_leaves_the_unnamed_register_alone(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('13G yy 8G Vj "_d')
        assert ed.text == deck_without(7, 8)
        assert ed.register() == (BOLT,)


# -- y Y -------------------------------------------------------------------------


@pytest.mark.parametrize("key", YANKERS)
async def test_yank_copies_the_selected_lines(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key}")
        assert ed.register() == (GOBLIN, EIDOLON)


@pytest.mark.parametrize("key", YANKERS)
async def test_yank_leaves_the_deck_unchanged(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key}")
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.parametrize("key", YANKERS)
async def test_yank_moves_the_cursor_to_the_top_of_the_selection(
    tmp_path: Path, key: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key}")
        assert ed.row == 7


@pytest.mark.parametrize("key", YANKERS)
async def test_yank_returns_to_normal_mode(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key}")
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("visual:y")
async def test_yank_into_a_named_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G Vj "ay')
        assert ed.register("a") == (GOBLIN, EIDOLON)


@pytest.mark.primitive("visual:y")
async def test_uppercase_register_appends_the_selection(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('13G "ayy 8G Vj "Ay')
        assert ed.register("a") == (BOLT, GOBLIN, EIDOLON)


@pytest.mark.primitive("visual:Y")
async def test_capital_y_into_the_clipboard_register_copies_to_the_clipboard(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G Vj "+Y')
    assert clipboard.text == f"{GOBLIN}\n{EIDOLON}\n"


@pytest.mark.primitive("visual:y")
async def test_yank_into_the_clipboard_register_copies_to_the_clipboard(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G Vj "+y')
    assert clipboard.text == f"{GOBLIN}\n{EIDOLON}\n"


# -- c S C -------------------------------------------------------------------------


@pytest.mark.parametrize("key", CHANGERS)
async def test_change_deletes_the_lines_and_opens_card_search(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key}")
        assert ed.mode is Mode.INSERT
        assert "4 Goblin Guide" not in ed.cards
        assert "2 Eidolon of the Great Revel" not in ed.cards


@pytest.mark.parametrize("key", CHANGERS)
async def test_change_puts_the_lines_in_the_unnamed_register(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key}")
        assert ed.register() == (GOBLIN, EIDOLON)


@pytest.mark.parametrize("key", CHANGERS)
async def test_change_then_escape_leaves_the_lines_deleted(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key} <Esc>")
        assert ed.mode is Mode.NORMAL
        assert ed.text == deck_without(7, 8)


@pytest.mark.parametrize("key", CHANGERS)
async def test_change_then_escape_undoes_in_one_step(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key} <Esc> u")
        assert ed.text == DECK


@pytest.mark.primitive("visual:c")
async def test_change_replaces_the_selection_with_the_searched_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj c lava")
        await settle(ed)
        ed.press("<CR>")
        assert "1 Lava Spike" in ed.cards
        assert "4 Goblin Guide" not in ed.cards
        assert "2 Eidolon of the Great Revel" not in ed.cards


@pytest.mark.primitive("visual:c")
async def test_change_with_a_card_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj c lava")
        await settle(ed)
        ed.press("<CR> <Esc> u")
        assert ed.text == DECK


# -- p P ---------------------------------------------------------------------------


@pytest.mark.primitive("visual:p")
async def test_p_replaces_the_selection_with_the_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G Vj p")
        assert ed.text == deck_replacing(12, 13, [GOBLIN])


@pytest.mark.primitive("visual:p")
async def test_p_leaves_the_replaced_lines_in_the_unnamed_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G Vj p")
        assert ed.register() == (BOLT, FIRE_ICE)


@pytest.mark.primitive("visual:p")
async def test_p_then_p_puts_the_replaced_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G Vj p p")
        assert ed.text == deck_replacing(12, 13, [GOBLIN, BOLT, FIRE_ICE])


@pytest.mark.primitive("visual:p")
async def test_p_with_a_count_puts_that_many_copies(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G Vj 3p")
        assert ed.text == deck_replacing(12, 13, [GOBLIN, GOBLIN, GOBLIN])


@pytest.mark.primitive("visual:p")
async def test_p_leaves_the_cursor_on_the_first_put_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G Vj p")
        assert ed.row == 12
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("visual:p")
async def test_p_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G Vj 3p u")
        assert ed.text == DECK


@pytest.mark.primitive("visual:p")
async def test_p_from_an_empty_register_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("13G Vj p")
        assert ed.text == DECK
        assert ed.is_error is True
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("visual:P")
async def test_capital_p_replaces_the_selection_with_the_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G Vj P")
        assert ed.text == deck_replacing(12, 13, [GOBLIN])


@pytest.mark.primitive("visual:P")
async def test_capital_p_leaves_every_register_as_it_was(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('9G "ayy 8G yy 13G Vj P')
        assert ed.register() == (GOBLIN,)
        assert ed.register("a") == (EIDOLON,)


@pytest.mark.primitive("visual:P")
async def test_capital_p_twice_puts_the_same_register_again(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        # The first P turns two lines into one, so Mountain moves up to row 16
        ed.press("8G yy 13G Vj P 17G V P")
        assert ed.lines[12] == GOBLIN
        assert ed.lines[16] == GOBLIN
        assert "16 Mountain" not in ed.cards


@pytest.mark.primitive("visual:P")
async def test_capital_p_from_a_named_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('9G "ayy 13G Vj "aP')
        assert ed.text == deck_replacing(12, 13, [EIDOLON])


@pytest.mark.primitive("visual:P")
async def test_capital_p_with_a_count_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G Vj 2P")
        assert ed.text == deck_replacing(12, 13, [GOBLIN, GOBLIN])
        assert ed.mode is Mode.NORMAL
        ed.press("u")
        assert ed.text == DECK


@pytest.mark.primitive("visual:d")
async def test_delete_at_the_end_of_the_deck_leaves_the_cursor_on_the_new_last_line(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press("20G Vj d")
        assert "SB:" not in ed.lines
        assert "2 Rest in Peace" not in ed.cards
        assert ed.row == len(ed.lines) - 1


@pytest.mark.primitive("visual:d")
async def test_delete_that_empties_a_section_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("13G Vj d")
        assert "    // Instant" not in ed.lines
        ed.press("u")
        assert ed.text == DECK

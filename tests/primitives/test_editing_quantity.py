"""Editing slice: the quantity keys + - and their vim names Ctrl-A Ctrl-X.

Spec (docs/keybindings.md, README Quantity): + / - increment and
decrement the quantity, a count scales them (10+), - at 0 deletes the
line, and both keep zone prefixes, @category, #tags and comments.
Ctrl-A / Ctrl-X are the same keys under vim's names.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, editor

pytestmark = pytest.mark.asyncio

L = DECK.splitlines(keepends=True)


def without(*rows: int) -> str:
    return "".join(text for i, text in enumerate(L) if i not in rows)


def replacing(row: int, text: str) -> str:
    return "".join(text + "\n" if i == row else old for i, old in enumerate(L))


NOT_CARDS = pytest.mark.parametrize(
    "goto",
    ["1G", "3G", "4G", "5G", "7G", "11G", "20G"],
    ids=["metadata", "empty-tags", "blank", "zone-header", "section-header",
         "blank-between-sections", "sideboard-header"],
)

TAGGED = (
    "// Deck: Tagged\n// Format: modern\n// Tags:\n\n"
    "4 Lightning Bolt  @burn  #fast  // the best\n"
    "SB: 2 Rest in Peace\n"
)


# ── + ─────────────────────────────────────────────────────────────────


@pytest.mark.primitive("+")
async def test_plus_adds_one_copy(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G +")
        assert ed.text == replacing(7, "    5 Goblin Guide")
        assert ed.modified is True
        assert ed.row == 7


@pytest.mark.primitive("+")
async def test_count_plus_adds_that_many(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 10+")
        assert ed.text == replacing(7, "    14 Goblin Guide")


@pytest.mark.primitive("+")
async def test_a_large_count_plus_reaches_three_digits(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("18G 100+")
        assert ed.text == replacing(17, "    116 Mountain")


@pytest.mark.primitive("+")
async def test_plus_works_on_the_last_card_in_the_sideboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G +")
        assert ed.text == replacing(20, "    3 Rest in Peace")


@pytest.mark.primitive("+")
async def test_plus_keeps_category_tags_and_comment(tmp_path: Path) -> None:
    async with editor(tmp_path, TAGGED) as ed:
        ed.press("5G +")
        assert ed.lines[4] == "5 Lightning Bolt  @burn  #fast  // the best"


@pytest.mark.primitive("+")
async def test_plus_keeps_a_zone_prefix(tmp_path: Path) -> None:
    async with editor(tmp_path, TAGGED) as ed:
        ed.press("6G +")
        assert ed.lines[5] == "SB: 3 Rest in Peace"


@pytest.mark.primitive("+")
@NOT_CARDS
async def test_plus_leaves_a_line_without_a_quantity_alone(tmp_path: Path, goto: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{goto} +")
        assert ed.text == DECK
        assert ed.modified is False


# ── - ─────────────────────────────────────────────────────────────────


@pytest.mark.primitive("-")
async def test_minus_removes_one_copy(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G -")
        assert ed.text == replacing(7, "    3 Goblin Guide")
        assert ed.modified is True


@pytest.mark.primitive("-")
async def test_count_minus_removes_that_many(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("18G 10-")
        assert ed.text == replacing(17, "    6 Mountain")


@pytest.mark.primitive("-")
async def test_minus_on_quantity_one_deletes_the_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("14G -")
        assert ed.text == without(13)


@pytest.mark.primitive("-")
async def test_minus_past_zero_deletes_the_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 5-")
        assert ed.text == without(7)


@pytest.mark.primitive("-")
async def test_minus_to_zero_on_the_only_sideboard_card_keeps_the_zone_header(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G 2-")
        assert ed.text == without(20)


@pytest.mark.primitive("-")
async def test_minus_emptying_a_section_drops_its_derived_header(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("14G - 13G 4-")
        assert ed.text == without(11, 12, 13, 14)


@pytest.mark.primitive("-")
async def test_minus_on_the_last_copy_in_a_one_card_deck_empties_it(tmp_path: Path) -> None:
    one = "// Deck: Solo\n// Format: modern\n// Tags:\n\n1 Lightning Bolt\n"
    async with editor(tmp_path, one) as ed:
        ed.press("5G -")
        assert ed.cards == []


@pytest.mark.primitive("-")
async def test_minus_keeps_category_tags_and_comment(tmp_path: Path) -> None:
    async with editor(tmp_path, TAGGED) as ed:
        ed.press("5G -")
        assert ed.lines[4] == "3 Lightning Bolt  @burn  #fast  // the best"


@pytest.mark.primitive("-")
async def test_minus_keeps_a_zone_prefix(tmp_path: Path) -> None:
    async with editor(tmp_path, TAGGED) as ed:
        ed.press("6G -")
        assert ed.lines[5] == "SB: 1 Rest in Peace"


@pytest.mark.primitive("-")
@NOT_CARDS
async def test_minus_leaves_a_line_without_a_quantity_alone(tmp_path: Path, goto: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{goto} -")
        assert ed.text == DECK
        assert ed.modified is False


# ── Ctrl-A, Ctrl-X ───────────────────────────────────────────────────


@pytest.mark.primitive("ctrl_a")
async def test_ctrl_a_adds_one_copy(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G <C-a>")
        assert ed.text == replacing(7, "    5 Goblin Guide")


@pytest.mark.primitive("ctrl_a")
async def test_count_ctrl_a_adds_that_many(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 3<C-a>")
        assert ed.text == replacing(7, "    7 Goblin Guide")


@pytest.mark.primitive("ctrl_a")
@NOT_CARDS
async def test_ctrl_a_leaves_a_line_without_a_quantity_alone(
    tmp_path: Path, goto: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{goto} <C-a>")
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive("ctrl_x")
async def test_ctrl_x_removes_one_copy(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G <C-x>")
        assert ed.text == replacing(7, "    3 Goblin Guide")


@pytest.mark.primitive("ctrl_x")
async def test_count_ctrl_x_removes_that_many(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 3<C-x>")
        assert ed.text == replacing(7, "    1 Goblin Guide")


@pytest.mark.primitive("ctrl_x")
async def test_ctrl_x_on_quantity_one_deletes_the_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("14G <C-x>")
        assert ed.text == without(13)


@pytest.mark.primitive("ctrl_x")
@NOT_CARDS
async def test_ctrl_x_leaves_a_line_without_a_quantity_alone(
    tmp_path: Path, goto: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{goto} <C-x>")
        assert ed.text == DECK
        assert ed.modified is False

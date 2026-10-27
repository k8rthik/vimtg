"""Editing slice: the line operators dd yy cc, their capitals S C D Y,
bare d y c as prefixes, and x.

Expected text comes from docs/keybindings.md (Editing), the README's
section model (a derived header with no cards is dropped, a bare zone
header never is), and vim's linewise behaviour where the docs are
silent. Rows are the 0-based rows of the canonical DECK (see harness).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, Ed, editor
from vimtg.editor.modes import Mode

pytestmark = pytest.mark.asyncio

L = DECK.splitlines(keepends=True)


def line(row: int) -> str:
    """Row `row` of DECK as a register holds it (no newline)."""
    return L[row].rstrip("\n")


def without(*rows: int) -> str:
    return "".join(text for i, text in enumerate(L) if i not in rows)


def section_cards(ed: Ed, header: str) -> list[str]:
    """Card lines (stripped) under the derived header `header` until the
    next blank line."""
    lines = [text.strip() for text in ed.lines]
    start = lines.index(header) + 1
    out = []
    for text in lines[start:]:
        if not text:
            break
        out.append(text)
    return out


# ── dd ────────────────────────────────────────────────────────────────


@pytest.mark.primitive("dd")
async def test_dd_deletes_the_card_under_the_cursor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G dd")
        assert ed.text == without(8)
        assert ed.line == "3 Bonecrusher Giant // Stomp"
        assert ed.modified is True


@pytest.mark.primitive("dd")
async def test_dd_fills_the_unnamed_and_first_delete_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G dd")
        assert ed.register('"') == (line(8),)
        assert ed.register("1") == (line(8),)


@pytest.mark.primitive("dd")
async def test_dd_leaves_the_yank_register_alone(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G dd")
        assert ed.register("0") == ()


@pytest.mark.primitive("dd")
async def test_count_dd_deletes_that_many_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 2dd")
        assert ed.text == without(7, 8)
        assert ed.register('"') == (line(7), line(8))


@pytest.mark.primitive("dd")
async def test_dd_of_the_first_card_keeps_the_rest_of_its_section(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G dd")
        assert ed.text == without(7)


@pytest.mark.primitive("dd")
async def test_emptying_a_section_drops_its_derived_header(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("13G 2dd")
        # // Instant goes with its cards, and one of the two blank lines
        # that framed it
        assert ed.text == without(11, 12, 13, 14)
        assert ed.register('"') == (line(12), line(13))


@pytest.mark.primitive("dd")
async def test_dd_of_the_only_sideboard_card_keeps_the_zone_header(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G dd")
        assert ed.text == without(20)
        assert ed.lines[-1] == "SB:"
        assert ed.row == 19


@pytest.mark.primitive("dd")
async def test_a_count_past_the_end_deletes_to_the_end(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("18G 9dd")
        assert ed.text == without(17, 18, 19, 20)


@pytest.mark.primitive("dd")
async def test_dd_on_a_section_header_deletes_that_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("12G dd")
        assert ed.text == without(11)
        assert ed.register('"') == (line(11),)


@pytest.mark.primitive("dd")
async def test_dd_of_the_last_card_in_a_one_card_deck_empties_it(tmp_path: Path) -> None:
    one = "// Deck: Solo\n// Format: modern\n// Tags:\n\n4 Lightning Bolt\n"
    async with editor(tmp_path, one) as ed:
        ed.press("5G dd")
        assert ed.cards == []
        assert ed.register('"') == ("4 Lightning Bolt",)
        assert ed.lines[:2] == ["// Deck: Solo", "// Format: modern"]


# ── yy ────────────────────────────────────────────────────────────────


@pytest.mark.primitive("yy")
async def test_yy_copies_the_line_without_changing_the_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G yy")
        assert ed.text == DECK
        assert ed.modified is False
        assert ed.row == 8


@pytest.mark.primitive("yy")
async def test_yy_fills_the_unnamed_and_yank_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G yy")
        assert ed.register('"') == (line(8),)
        assert ed.register("0") == (line(8),)
        assert ed.register("1") == ()


@pytest.mark.primitive("yy")
async def test_count_yy_yanks_that_many_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 3yy")
        assert ed.register('"') == (line(7), line(8), line(9))
        assert ed.text == DECK


@pytest.mark.primitive("yy")
async def test_count_yy_past_the_end_yanks_to_the_end(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G 5yy")
        assert ed.register('"') == (line(20),)


# ── cc, S, C ──────────────────────────────────────────────────────────


@pytest.mark.primitive("cc")
async def test_cc_deletes_the_line_and_opens_card_search(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G cc")
        assert ed.mode is Mode.INSERT
        assert "2 Eidolon of the Great Revel" not in ed.cards


@pytest.mark.primitive("cc")
async def test_cc_replaces_the_card_with_the_one_picked(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G cc")
        await ed.pick("delver")
        assert ed.mode is Mode.NORMAL
        creatures = section_cards(ed, "// Creature")
        assert "2 Eidolon of the Great Revel" not in creatures
        assert any("Delver of Secrets" in card for card in creatures)
        assert len(ed.cards) == 8
        assert ed.modified is True


@pytest.mark.primitive("cc")
async def test_cc_then_escape_leaves_the_line_deleted(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G cc <Esc>")
        assert ed.mode is Mode.NORMAL
        assert ed.text == without(8)


@pytest.mark.primitive("cc")
async def test_cc_files_the_deleted_line_as_a_delete(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G cc <Esc>")
        assert ed.register('"') == (line(8),)
        assert ed.register("1") == (line(8),)


@pytest.mark.primitive("cc")
async def test_count_cc_changes_that_many_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 2cc")
        await ed.pick("delver")
        creatures = section_cards(ed, "// Creature")
        assert "4 Goblin Guide" not in creatures
        assert "2 Eidolon of the Great Revel" not in creatures
        assert "3 Bonecrusher Giant // Stomp" in creatures
        assert any("Delver of Secrets" in card for card in creatures)


@pytest.mark.primitive("S", "C")
@pytest.mark.parametrize("key", ["S", "C"])
async def test_capital_change_keys_work_like_cc(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"9G {key}")
        assert ed.mode is Mode.INSERT
        await ed.pick("delver")
        creatures = section_cards(ed, "// Creature")
        assert "2 Eidolon of the Great Revel" not in creatures
        assert any("Delver of Secrets" in card for card in creatures)


@pytest.mark.primitive("S", "C")
@pytest.mark.parametrize("key", ["S", "C"])
async def test_capital_change_keys_take_a_count_and_register(
    tmp_path: Path, key: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f'8G "a2{key} <Esc>')
        assert ed.text == without(7, 8)
        assert ed.register("a") == (line(7), line(8))


# ── D, Y ──────────────────────────────────────────────────────────────


@pytest.mark.primitive("D")
async def test_capital_d_deletes_the_line_like_dd(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G D")
        assert ed.text == without(8)
        assert ed.register("1") == (line(8),)


@pytest.mark.primitive("D")
async def test_count_capital_d_deletes_that_many_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 2D")
        assert ed.text == without(7, 8)


@pytest.mark.primitive("Y")
async def test_capital_y_yanks_the_line_like_yy(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G Y")
        assert ed.text == DECK
        assert ed.modified is False
        assert ed.register("0") == (line(8),)


@pytest.mark.primitive("Y", '"{a-z}')
async def test_register_count_capital_y_yanks_lines_into_the_register(tmp_path: Path) -> None:
    # The docs' own example: "a3Y yanks three lines into a
    async with editor(tmp_path) as ed:
        ed.press('8G "a3Y')
        assert ed.register("a") == (line(7), line(8), line(9))
        assert ed.text == DECK


# ── bare d, y, c: prefixes ───────────────────────────────────────────


@pytest.mark.primitive("d")
async def test_d_waits_for_a_motion_without_deleting(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G d")
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive("d", "y", "c")
@pytest.mark.parametrize("op", ["d", "y", "c"])
async def test_escape_cancels_a_pending_operator(tmp_path: Path, op: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"9G {op} <Esc> j")
        # The j after Esc is a plain motion, not the operator's target
        assert ed.text == DECK
        assert ed.row == 9
        assert ed.mode is Mode.NORMAL
        assert ed.modified is False
        assert ed.register('"') == ()


@pytest.mark.primitive("d")
async def test_a_count_after_d_counts_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G d2d")
        assert ed.text == without(7, 8)


@pytest.mark.primitive("y")
async def test_counts_before_and_after_y_multiply(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("17G 2y2y")
        assert ed.register('"') == (line(16), line(17), line(18), line(19))
        assert ed.text == DECK


@pytest.mark.primitive("d")
async def test_counts_before_and_after_d_multiply(tmp_path: Path) -> None:
    flat = (
        "// Deck: Flat\n// Format: modern\n// Tags:\n\n"
        "1 Goblin Guide\n2 Eidolon of the Great Revel\n"
        "3 Bonecrusher Giant // Stomp\n4 Lightning Bolt\n5 Fire // Ice\n"
        "6 Sacred Foundry\n"
    )
    async with editor(tmp_path, flat) as ed:
        ed.press("5G 2d2d")
        assert ed.cards == ["5 Fire // Ice", "6 Sacred Foundry"]


@pytest.mark.primitive("c")
async def test_a_count_after_c_counts_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G c2c")
        assert ed.mode is Mode.INSERT
        ed.press("<Esc>")
        assert ed.text == without(7, 8)


# ── x ─────────────────────────────────────────────────────────────────


@pytest.mark.primitive("x")
async def test_x_deletes_the_card_under_the_cursor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G x")
        assert ed.text == without(8)
        assert ed.modified is True


@pytest.mark.primitive("x")
async def test_x_puts_the_card_in_the_delete_registers(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G x")
        assert ed.register('"') == (line(8),)
        assert ed.register("1") == (line(8),)


@pytest.mark.primitive("x")
async def test_count_x_deletes_consecutive_cards(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 2x")
        assert ed.text == without(7, 8)
        assert ed.register('"') == (line(7), line(8))


@pytest.mark.primitive("x")
async def test_count_x_stops_at_the_first_non_card_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("13G 5x")
        # Bolt and Fire // Ice go; the blank and // Land stay, and the
        # emptied // Instant header is dropped
        assert ed.text == without(11, 12, 13, 14)
        assert ed.register('"') == (line(12), line(13))


@pytest.mark.primitive("x")
async def test_x_deletes_the_last_card_of_the_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G x")
        assert ed.text == without(20)


@pytest.mark.primitive("x")
@pytest.mark.parametrize(
    "goto",
    ["1G", "3G", "4G", "5G", "7G", "11G", "20G"],
    ids=["metadata", "empty-tags", "blank", "zone-header", "section-header",
         "blank-between-sections", "sideboard-header"],
)
async def test_x_refuses_a_line_that_is_not_a_card(tmp_path: Path, goto: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{goto} x")
        assert ed.text == DECK
        assert ed.modified is False
        assert ed.register('"') == ()

"""Editing slice: registers ("{a-z} "_ "+ "*), :registers, and put (p P).

Spec: docs/keybindings.md (Editing; Marks, macros, registers) and the
README's Registers line. Where they are silent, vim's register rules
are the reference: "0 holds the last yank made without a named
register, "1-"9 shift on every delete, the unnamed register follows
the last yank or delete, and a linewise put leaves the cursor on the
first new line.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeClipboard
from tests.primitives.harness import DECK, editor

pytestmark = pytest.mark.asyncio

L = DECK.splitlines(keepends=True)


def line(row: int) -> str:
    return L[row].rstrip("\n")


def without(*rows: int) -> str:
    return "".join(text for i, text in enumerate(L) if i not in rows)


def inserting(before: int, *rows: int) -> str:
    """DECK with the lines at `rows` inserted before row `before`."""
    added = [L[r] for r in rows]
    return "".join(L[:before] + added + L[before:])


# ── named registers "a-"z and "A-"Z ─────────────────────────────────


@pytest.mark.primitive('"{a-z}', "yy")
async def test_yank_into_a_named_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "ayy')
        assert ed.register("a") == (line(7),)
        assert ed.text == DECK


@pytest.mark.primitive('"{a-z}', "dd")
async def test_delete_into_a_named_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('9G "add')
        assert ed.register("a") == (line(8),)
        assert ed.text == without(8)


@pytest.mark.primitive('"{a-z}', "p")
async def test_put_from_a_named_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "ayy 9G yy 13G "ap')
        assert ed.text == inserting(13, 7)


@pytest.mark.primitive('"{a-z}')
async def test_named_registers_are_independent(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "ayy 9G "byy')
        assert ed.register("a") == (line(7),)
        assert ed.register("b") == (line(8),)


@pytest.mark.primitive('"{a-z}')
async def test_a_named_yank_also_sets_the_unnamed_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "ayy')
        assert ed.register('"') == (line(7),)


@pytest.mark.primitive('"{a-z}')
async def test_a_named_yank_leaves_the_yank_register_alone(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('9G yy 8G "ayy')
        assert ed.register("0") == (line(8),)


@pytest.mark.primitive('"{a-z}')
async def test_uppercase_register_appends_a_yank(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "ayy 13G "Ayy')
        assert ed.register("a") == (line(7), line(12))


@pytest.mark.primitive('"{a-z}')
async def test_uppercase_register_appends_a_delete(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "ayy 9G "Add')
        assert ed.register("a") == (line(7), line(8))
        assert ed.text == without(8)


@pytest.mark.primitive('"{a-z}')
async def test_uppercase_register_on_an_empty_register_starts_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "Ayy')
        assert ed.register("a") == (line(7),)


@pytest.mark.primitive('"{a-z}', "yy")
async def test_a_count_before_the_register_still_counts_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G 2"ayy')
        assert ed.register("a") == (line(7), line(8))


@pytest.mark.primitive('"{a-z}', "x")
async def test_x_deletes_into_a_named_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('9G "cx')
        assert ed.register("c") == (line(8),)
        assert ed.text == without(8)


@pytest.mark.primitive('"{a-z}')
async def test_escape_after_a_register_name_cancels_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "a <Esc> yy')
        assert ed.register("a") == ()
        assert ed.register('"') == (line(7),)


# ── the yank register "0 and the delete history "1-"9 ─────────────────


@pytest.mark.primitive("yy", "dd")
async def test_the_yank_register_survives_a_delete(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 9G dd")
        assert ed.register("0") == (line(7),)
        assert ed.register('"') == (line(8),)


@pytest.mark.primitive("p", "dd")
async def test_put_from_the_yank_register_after_a_delete(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G yy 14G dd 13G "0p')
        # Fire // Ice went; Goblin Guide lands below Lightning Bolt
        assert ed.text == "".join(L[:13] + [L[7]] + L[14:])


@pytest.mark.primitive("dd")
async def test_deletes_shift_through_the_numbered_registers(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G dd dd dd")
        assert ed.register("1") == (line(9),)
        assert ed.register("2") == (line(8),)
        assert ed.register("3") == (line(7),)


@pytest.mark.primitive("dd")
async def test_the_ninth_delete_register_drops_the_oldest(tmp_path: Path) -> None:
    flat = "// Deck: Flat\n// Format: modern\n// Tags:\n\n" + "".join(
        f"{n} Card {n}\n" for n in range(1, 12)
    )
    async with editor(tmp_path, flat, cards=False) as ed:
        ed.press("5G " + "dd " * 10)
        assert ed.register("1") == ("10 Card 10",)
        assert ed.register("9") == ("2 Card 2",)


@pytest.mark.primitive("yy", "dd")
async def test_a_yank_does_not_shift_the_delete_history(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G dd 8G yy")
        assert ed.register("1") == (line(8),)
        assert ed.register("2") == ()


@pytest.mark.primitive("p", "dd")
async def test_put_from_the_first_delete_register(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('9G dd 8G yy G "1p')
        assert ed.lines[-1] == line(8)


# ── the black hole "_ ──────────────────────────────────────────────────


@pytest.mark.primitive('"_', "dd")
async def test_black_hole_delete_still_deletes(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('9G "_dd')
        assert ed.text == without(8)
        assert ed.modified is True


@pytest.mark.primitive('"_', "dd")
async def test_black_hole_delete_leaves_every_register_alone(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G yy 13G dd 9G "_dd')
        assert ed.register('"') == (line(12),)
        assert ed.register("0") == (line(7),)
        assert ed.register("1") == (line(12),)
        assert ed.register("2") == ()


@pytest.mark.primitive('"_', "p")
async def test_put_after_a_black_hole_delete_puts_the_earlier_text(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G yy 9G "_dd p')
        # Eidolon is gone; Goblin Guide is put below the line that took
        # its place (Bonecrusher Giant, now row 8)
        assert ed.text == "".join(L[:8] + [L[9], L[7]] + L[10:])


@pytest.mark.primitive('"_', "yy")
async def test_black_hole_yank_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G yy 9G "_yy')
        assert ed.register('"') == (line(7),)
        assert ed.register("0") == (line(7),)


@pytest.mark.primitive('"_', "x")
async def test_black_hole_x_leaves_registers_alone(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G yy 9G "_x')
        assert ed.text == without(8)
        assert ed.register('"') == (line(7),)
        assert ed.register("1") == ()


# ── the clipboard register "+ / "* ─────────────────────────────────────


@pytest.mark.primitive('"+', "yy")
async def test_clipboard_yank_reaches_the_system_clipboard(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "+yy')
        assert ed.message.startswith("Copied")
        assert not ed.is_error
    # The register's text verbatim, indentation included: the docs say a
    # yank "also copies" to the clipboard, vim copies the line as is, and
    # vimtg's own importer reads the indented line as 4 Goblin Guide
    assert clipboard.text == "    4 Goblin Guide\n"
    assert clipboard.copies == ["    4 Goblin Guide\n"]


@pytest.mark.primitive('"+', "yy")
async def test_clipboard_yank_of_several_lines(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G 3"+yy')
    assert clipboard.text == L[7] + L[8] + L[9]


@pytest.mark.primitive('"+', "dd")
async def test_clipboard_delete_reaches_the_system_clipboard(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('9G "+dd')
        assert ed.text == without(8)
    assert clipboard.text == L[8]


@pytest.mark.primitive('"+', "x")
async def test_clipboard_x_reaches_the_system_clipboard(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('9G "+x')
    assert clipboard.text == L[8]


@pytest.mark.primitive('"+', "yy")
async def test_clipboard_yank_also_sets_the_unnamed_register(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "+yy 13G p')
        assert ed.text == inserting(13, 7)


@pytest.mark.primitive("yy", "dd", '"{a-z}')
async def test_other_registers_never_touch_the_system_clipboard(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G yy "ayy 9G dd "bdd x')
    assert clipboard.copies == []


@pytest.mark.primitive('"+', "p")
async def test_clipboard_put_puts_what_was_yanked_to_it(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "+yy 9G yy 13G "+p')
        assert ed.text == inserting(13, 7)


@pytest.mark.primitive('"+', "p")
async def test_clipboard_put_never_reads_the_system_clipboard(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    clipboard.text = "4 Mountain\n"
    async with editor(tmp_path) as ed:
        ed.press('8G "+p')
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive('"*', "yy")
async def test_star_yank_reaches_the_system_clipboard(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "*yy')
        assert ed.message.startswith("Copied")
    assert clipboard.text == L[7]


@pytest.mark.primitive('"*', '"+', "p")
async def test_star_and_plus_are_one_register(
    tmp_path: Path, clipboard: FakeClipboard
) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "*yy 9G yy 13G "+p')
        assert ed.text == inserting(13, 7)
        ed.press('9G "+yy 13G "*p')
        assert ed.lines[13] == line(8)


# ── :registers ──────────────────────────────────────────────────────


@pytest.mark.primitive(":registers")
async def test_registers_lists_what_each_register_holds(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "ayy 14G "bdd :registers<CR>')
        assert '"a 4 Goblin Guide' in ed.message
        assert '"b 1 Fire // Ice' in ed.message
        assert not ed.is_error


@pytest.mark.primitive(":registers")
async def test_registers_leaves_out_empty_registers(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "ayy :registers<CR>')
        assert '"b' not in ed.message
        assert '"_' not in ed.message


@pytest.mark.primitive(":registers")
async def test_registers_with_names_shows_only_those(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "ayy 9G "byy :registers<Space>a<CR>')
        assert '"a 4 Goblin Guide' in ed.message
        assert '"b' not in ed.message


@pytest.mark.primitive(":registers")
async def test_registers_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press('8G "ayy :registers<CR>')
        assert ed.text == DECK
        assert ed.modified is False


# ── p / P ───────────────────────────────────────────────────────────


@pytest.mark.primitive("p")
async def test_p_puts_below_the_cursor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G p")
        assert ed.text == inserting(13, 7)
        assert ed.row == 13
        assert ed.modified is True


@pytest.mark.primitive("P")
async def test_capital_p_puts_above_the_cursor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G P")
        assert ed.text == inserting(12, 7)
        assert ed.row == 12
        assert ed.modified is True


@pytest.mark.primitive("p")
async def test_count_p_puts_that_many_copies(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G 3p")
        assert ed.text == inserting(13, 7, 7, 7)


@pytest.mark.primitive("p")
@pytest.mark.xfail(
    strict=True,
    reason="BUG: 3p leaves the cursor on the last put line (row 15); vim leaves it "
    "on the first (row 13) and the docs do not say",
)
async def test_count_p_leaves_the_cursor_on_the_first_new_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G 3p")
        assert ed.row == 13


@pytest.mark.primitive("P")
async def test_count_capital_p_puts_that_many_copies_above(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G 3P")
        assert ed.text == inserting(12, 7, 7, 7)
        assert ed.row == 12


@pytest.mark.primitive("p")
async def test_p_of_several_lines_keeps_their_order(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 2yy 13G p")
        assert ed.text == inserting(13, 7, 8)


@pytest.mark.primitive("p")
async def test_p_moves_a_deleted_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G dd 12G p")
        # Goblin Guide leaves // Creature and lands below Lightning Bolt
        assert ed.text == "".join(L[:7] + L[8:13] + [L[7]] + L[13:])


@pytest.mark.primitive("p")
async def test_p_puts_a_sideboard_card_into_the_main_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G yy 8G p")
        assert ed.text == inserting(8, 20)
        assert ed.cards.count("2 Rest in Peace") == 2


@pytest.mark.primitive("p")
async def test_p_at_the_end_of_the_deck_puts_into_the_sideboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy G p")
        assert ed.text == DECK + L[7]
        assert ed.row == 21


@pytest.mark.primitive("p")
async def test_p_below_a_section_header_tops_that_section(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 12G p")
        assert ed.text == inserting(12, 7)


@pytest.mark.primitive("p", "P")
@pytest.mark.parametrize("key", ["p", "P"])
async def test_put_with_an_empty_register_changes_nothing(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G {key}")
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive("p", "P")
@pytest.mark.parametrize("key", ["p", "P"])
async def test_put_from_an_empty_named_register_changes_nothing(
    tmp_path: Path, key: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f'8G yy "z{key}')
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive("p")
async def test_put_does_not_change_the_registers(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G yy 13G p")
        assert ed.register('"') == (line(7),)
        assert ed.register("1") == ()

"""Input slice: entering insert, the card search, line edit and comments.

Expected values come from docs/keybindings.md (Modes, Card search) and
the README's card-search and placement notes. Card search runs on a
worker thread, so every case that needs results awaits `ed.settle()`
(the app's workers) before reading or confirming them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, Ed, editor
from vimtg.editor.modes import Mode
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.search_results import SearchResults

DELVER = "Delver of Secrets // Insectile Aberration"


def typed(text: str) -> str:
    """Key notation for literal text: spaces become <Space>."""
    return text.replace(" ", "<Space>")


def results(ed: Ed) -> SearchResults:
    return ed.screen.query_one("#search-results", SearchResults)


def query(ed: Ed) -> str:
    return ed.screen.query_one("#command-line", CommandLine).text


def section_of(ed: Ed, card: str) -> str:
    """The nearest '// ...' header above the card's line."""
    row = next(i for i, line in enumerate(ed.lines) if line.strip() == card)
    for i in range(row - 1, -1, -1):
        line = ed.lines[i].strip()
        if line.startswith("// ") and ":" not in line:
            return line
    return ""


def zone_of(ed: Ed, card: str) -> str:
    """The zone block header ('DCK:', 'SB:') the card's line sits in."""
    row = next(i for i, line in enumerate(ed.lines) if line.strip() == card)
    for i in range(row - 1, -1, -1):
        if ed.lines[i] in ("DCK:", "SB:", "MB:", "CMD:", "CMP:"):
            return ed.lines[i]
    return ""


async def add_card(ed: Ed, prefix: str, name_query: str) -> None:
    """`prefix` (e.g. '8G o', '4o') opens the search; confirm the top hit."""
    ed.press(prefix + typed(name_query))
    await ed.settle()
    ed.press("<CR>")


# ── i: line edit ─────────────────────────────────────────────────


@pytest.mark.primitive("i", "insert:type")
@pytest.mark.asyncio
async def test_i_rewrites_the_card_line_in_place(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G i")
        assert ed.mode is Mode.INSERT
        ed.press("<C-u>" + typed("3 Goblin Guide") + "<CR>")
        assert ed.mode is Mode.NORMAL
        expected = DECK.replace("    4 Goblin Guide", "    3 Goblin Guide")
        assert ed.text == expected
        assert ed.modified is True


@pytest.mark.primitive("i", "insert:backspace")
@pytest.mark.asyncio
async def test_i_backspace_stops_at_the_block_indentation(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G i" + "<BS>" * 30 + typed("2 Lava Spike") + "<CR>")
        assert ed.lines[7] == "    2 Lava Spike"


@pytest.mark.primitive("i")
@pytest.mark.asyncio
async def test_i_on_metadata_edits_only_the_value(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("1G i <C-u>" + typed("Zoo") + "<CR>")
        assert ed.lines[0] == "// Deck: Zoo"
        assert ed.lines[1:] == DECK.splitlines()[1:]


@pytest.mark.primitive("i", "insert:backspace")
@pytest.mark.asyncio
async def test_i_renames_a_section_header_in_place(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("7G i" + "<BS>" * len("Creature") + "Threats<CR>")
        assert ed.lines[6] == "    // Threats"
        assert ed.lines[7:10] == DECK.splitlines()[7:10]


@pytest.mark.primitive("i", "insert:type")
@pytest.mark.asyncio
async def test_i_on_a_blank_line_in_a_block_keeps_the_card_in_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("15G i" + typed("1 Lava Spike") + "<CR>")
        assert ed.lines[14] == "    1 Lava Spike"


@pytest.mark.primitive("i")
@pytest.mark.asyncio
async def test_i_on_a_bare_zone_header_is_refused(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("5G i")
        assert ed.mode is Mode.NORMAL
        assert ed.is_error
        assert "E21" in ed.message
        assert ed.text == DECK


@pytest.mark.primitive("i", "insert:escape")
@pytest.mark.asyncio
async def test_escape_from_line_edit_restores_the_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G i <C-u> xyz <Esc>")
        assert ed.mode is Mode.NORMAL
        assert ed.text == DECK
        assert ed.modified is False


@pytest.mark.primitive("i")
@pytest.mark.asyncio
async def test_one_undo_reverts_a_line_edit(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G i <C-u>" + typed("3 Goblin Guide") + "<CR> u")
        assert ed.text == DECK


# ── A: inline comment ────────────────────────────────────────────


@pytest.mark.primitive("A")
@pytest.mark.asyncio
async def test_cap_a_adds_an_inline_comment(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G A" + typed("fast clock") + "<CR>")
        assert ed.lines[7] == "    4 Goblin Guide  // fast clock"
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("A")
@pytest.mark.asyncio
async def test_cap_a_edits_an_existing_comment(tmp_path: Path) -> None:
    deck = DECK.replace("4 Goblin Guide", "4 Goblin Guide  // fast")
    async with editor(tmp_path, deck) as ed:
        ed.press("8G A")
        assert query(ed) == "fast"
        ed.press("<C-u> slow <CR>")
        assert ed.lines[7] == "    4 Goblin Guide  // slow"


@pytest.mark.primitive("A")
@pytest.mark.asyncio
async def test_cap_a_confirming_empty_text_removes_the_comment(tmp_path: Path) -> None:
    deck = DECK.replace("4 Goblin Guide", "4 Goblin Guide  // fast")
    async with editor(tmp_path, deck) as ed:
        ed.press("8G A <C-u> <CR>")
        assert ed.text == DECK


@pytest.mark.primitive("A", "insert:escape")
@pytest.mark.asyncio
async def test_cap_a_escape_leaves_the_line_alone(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G A note <Esc>")
        assert ed.text == DECK
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("A")
@pytest.mark.asyncio
async def test_one_undo_reverts_a_comment(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G A note <CR> u")
        assert ed.text == DECK


# ── o / O: card search placement ─────────────────────────────────


# With auto_sort on (the default) a new card is filed "instead of at the
# cursor" (README, Configuration), so below / above is pinned with it off.
NOAUTOSORT = ":set<Space>noautosort<CR>"


@pytest.mark.primitive("o", "insert:type", "insert:enter")
@pytest.mark.asyncio
async def test_o_adds_one_copy_below_the_cursor_without_auto_sort(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, NOAUTOSORT + "8G o", "delver")
        assert ed.mode is Mode.NORMAL
        assert ed.lines[8] == f"    1 {DELVER}"
        assert ed.lines[7] == "    4 Goblin Guide"
        assert ed.row == 8
        assert len(ed.lines) == len(DECK.splitlines()) + 1


@pytest.mark.primitive("O", "insert:enter")
@pytest.mark.asyncio
async def test_cap_o_adds_the_card_above_the_cursor_without_auto_sort(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, NOAUTOSORT + "9G O", "delver")
        assert ed.lines[8] == f"    1 {DELVER}"
        assert ed.lines[9] == "    2 Eidolon of the Great Revel"
        assert ed.row == 8


@pytest.mark.primitive("o")
@pytest.mark.asyncio
async def test_counted_o_sets_the_quantity(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, "8G 4o", "delver")
        assert f"4 {DELVER}" in ed.cards


@pytest.mark.primitive("o")
@pytest.mark.asyncio
async def test_o_files_the_card_into_its_own_type_section(tmp_path: Path) -> None:
    deck = DECK.replace("    4 Lightning Bolt\n", "")
    async with editor(tmp_path, deck) as ed:
        await add_card(ed, "8G o", "lightning")
        assert "1 Lightning Bolt" in ed.cards
        assert section_of(ed, "1 Lightning Bolt") == "// Instant"
        assert ed.lines[ed.row].strip() == "1 Lightning Bolt"


@pytest.mark.primitive("o")
@pytest.mark.asyncio
async def test_o_with_no_matching_section_creates_one_in_the_mainboard(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, "8G o", "lava")
        assert ed.cards.count("1 Lava Spike") == 1
        assert section_of(ed, "1 Lava Spike") in ("// Sorcery", "// Sorceries")
        assert zone_of(ed, "1 Lava Spike") == "DCK:"


@pytest.mark.primitive("o", "insert:enter")
@pytest.mark.asyncio
async def test_o_on_a_card_already_in_the_zone_bumps_its_quantity(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, "8G o", "lightning")
        assert ed.text == DECK.replace("4 Lightning Bolt", "5 Lightning Bolt")


@pytest.mark.primitive("o")
@pytest.mark.asyncio
async def test_counted_o_on_a_duplicate_adds_that_many(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, "8G 3o", "lightning")
        assert ed.text == DECK.replace("4 Lightning Bolt", "7 Lightning Bolt")


@pytest.mark.primitive("o")
@pytest.mark.asyncio
async def test_o_in_the_mainboard_never_bumps_the_sideboard_copy(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, "8G o", "rest in")
        assert ed.cards.count("1 Rest in Peace") == 1
        assert zone_of(ed, "1 Rest in Peace") == "DCK:"
        assert ed.lines[-1] == "    2 Rest in Peace"


@pytest.mark.primitive("o")
@pytest.mark.asyncio
async def test_o_inside_the_sideboard_block_lands_there(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, "21G o", "lava")
        assert zone_of(ed, "1 Lava Spike") == "SB:"
        assert ed.lines[:20] == DECK.splitlines()[:20]
        assert sorted(ed.cards[-2:]) == ["1 Lava Spike", "2 Rest in Peace"]


@pytest.mark.primitive("o")
@pytest.mark.asyncio
async def test_o_inside_the_sideboard_lands_below_without_auto_sort(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, NOAUTOSORT + "21G o", "lava")
        assert ed.lines[20] == "    2 Rest in Peace"
        assert ed.lines[21] == "    1 Lava Spike"


@pytest.mark.primitive("O")
@pytest.mark.asyncio
async def test_cap_o_inside_the_sideboard_lands_above_without_auto_sort(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, NOAUTOSORT + "21G O", "lava")
        assert ed.lines[20] == "    1 Lava Spike"
        assert ed.lines[21] == "    2 Rest in Peace"


@pytest.mark.primitive("o")
@pytest.mark.asyncio
async def test_o_on_a_sideboard_duplicate_bumps_the_sideboard_line(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, "21G o", "rest in")
        assert ed.text == DECK.replace("2 Rest in Peace", "3 Rest in Peace")


@pytest.mark.primitive("o")
@pytest.mark.asyncio
async def test_o_on_a_section_header_files_into_the_mainboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, "7G o", "delver")
        assert section_of(ed, f"1 {DELVER}") == "// Creature"
        assert zone_of(ed, f"1 {DELVER}") == "DCK:"


@pytest.mark.primitive("o")
@pytest.mark.asyncio
async def test_o_on_a_blank_line_files_into_the_mainboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, "15G o", "delver")
        assert section_of(ed, f"1 {DELVER}") == "// Creature"
        assert zone_of(ed, f"1 {DELVER}") == "DCK:"


@pytest.mark.primitive("o")
@pytest.mark.asyncio
async def test_o_on_a_metadata_row_files_into_the_mainboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, "1G o", "delver")
        assert ed.lines[:3] == ["// Deck: Burn", "// Format: modern", "// Tags:"]
        assert section_of(ed, f"1 {DELVER}") == "// Creature"
        assert zone_of(ed, f"1 {DELVER}") == "DCK:"


@pytest.mark.primitive("o", "insert:escape")
@pytest.mark.asyncio
async def test_escape_cancels_o_and_restores_the_cursor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G o del")
        await ed.settle()
        ed.press("<Esc>")
        assert ed.mode is Mode.NORMAL
        assert ed.text == DECK
        assert ed.row == 7
        assert ed.modified is False
        assert not results(ed).display


@pytest.mark.primitive("O", "insert:escape")
@pytest.mark.asyncio
async def test_escape_cancels_cap_o_and_restores_the_cursor(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9G O <Esc>")
        assert ed.text == DECK
        assert ed.row == 8


@pytest.mark.primitive("o", "O")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prefix", "name"),
    [(NOAUTOSORT + "8G o", "delver"), (NOAUTOSORT + "9G O", "delver"), ("8G 4o", "delver"),
     ("8G o", "lightning"), ("21G o", "lava"), ("8G o", "lava")],
)
async def test_one_undo_reverts_an_added_card(
    tmp_path: Path, prefix: str, name: str,
) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, prefix, name)
        assert ed.text != DECK
        ed.press("u")
        assert ed.text == DECK


# ── insert keys inside the card search ───────────────────────────


@pytest.mark.primitive("insert:type")
@pytest.mark.asyncio
async def test_typing_shows_results_from_two_characters(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G o l")
        await ed.settle()
        assert query(ed) == "l"
        assert not results(ed).display
        ed.press("a")
        await ed.settle()
        assert query(ed) == "la"
        assert results(ed).display
        assert [c.name for c in results(ed).results] == ["Lava Spike"]


@pytest.mark.primitive("insert:type")
@pytest.mark.asyncio
async def test_typing_an_unknown_key_names_it_in_the_overlay(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G o foo:bar")
        await ed.settle()
        assert "foo" in results(ed).error
        ed.press("<CR>")
        assert ed.text == DECK
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("insert:type")
@pytest.mark.asyncio
async def test_ctrl_u_in_the_card_search_clears_the_query(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        await add_card(ed, "8G o", "zzz<C-u>delver")
        assert section_of(ed, f"1 {DELVER}") == "// Creature"


@pytest.mark.primitive("insert:backspace")
@pytest.mark.asyncio
async def test_backspace_edits_the_query(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G o lavx")
        await ed.settle()
        assert results(ed).results == []
        ed.press("<BS>")
        await ed.settle()
        assert query(ed) == "lav"
        assert [c.name for c in results(ed).results] == ["Lava Spike"]
        ed.press("<CR>")
        assert "1 Lava Spike" in ed.cards


@pytest.mark.primitive("insert:tab")
@pytest.mark.asyncio
async def test_tab_selects_the_next_result(tmp_path: Path) -> None:
    # t:creature, ranked by name: Bonecrusher, Delver, Eidolon, Goblin
    async with editor(tmp_path) as ed:
        ed.press("8G o t:creature")
        await ed.settle()
        names = [c.name for c in results(ed).results]
        assert names == [
            "Bonecrusher Giant // Stomp", DELVER,
            "Eidolon of the Great Revel", "Goblin Guide",
        ]
        ed.press("<Tab> <CR>")
        assert f"1 {DELVER}" in ed.cards
        assert "3 Bonecrusher Giant // Stomp" in ed.cards


@pytest.mark.primitive("insert:tab")
@pytest.mark.asyncio
async def test_tab_twice_selects_the_third_result(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G o t:creature")
        await ed.settle()
        ed.press("<Tab> <Tab> <CR>")
        assert ed.text == DECK.replace(
            "2 Eidolon of the Great Revel", "3 Eidolon of the Great Revel"
        )


@pytest.mark.primitive("insert:shift_tab")
@pytest.mark.asyncio
async def test_shift_tab_selects_the_previous_result(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G o t:creature")
        await ed.settle()
        ed.press("<Tab> <Tab> <S-Tab> <CR>")
        assert f"1 {DELVER}" in ed.cards
        assert "2 Eidolon of the Great Revel" in ed.cards


@pytest.mark.primitive("insert:enter")
@pytest.mark.asyncio
async def test_enter_with_no_match_adds_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G o zzzz")
        await ed.settle()
        ed.press("<CR>")
        assert ed.mode is Mode.NORMAL
        assert ed.text == DECK
        assert ed.row == 7
        assert ed.modified is False


@pytest.mark.primitive("insert:enter")
@pytest.mark.asyncio
async def test_enter_before_any_results_adds_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G o <CR>")
        assert ed.mode is Mode.NORMAL
        assert ed.text == DECK


# ── escape in normal mode ────────────────────────────────────────


@pytest.mark.primitive("escape")
@pytest.mark.asyncio
async def test_escape_cancels_a_pending_operator(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G d <Esc> j")
        assert ed.text == DECK
        assert ed.row == 8


@pytest.mark.primitive("escape")
@pytest.mark.asyncio
async def test_escape_cancels_a_pending_count(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G 3 <Esc> j")
        assert ed.row == 8


@pytest.mark.primitive("escape")
@pytest.mark.asyncio
async def test_escape_in_normal_mode_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G <Esc>")
        assert ed.mode is Mode.NORMAL
        assert ed.text == DECK
        assert ed.row == 7

"""Visual mode: quantity keys (+ - Ctrl-A Ctrl-X) and the z zone and plan
keys acting on every card in the selection.

Per docs/keybindings.md each acts on every selected card, ignores the
headers and blanks in between, ends the selection, and is one undo step.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.primitives.harness import DECK, Ed, editor
from vimtg.editor.modes import Mode

pytestmark = pytest.mark.asyncio

ROWS = DECK.splitlines()


def deck_with(changes: dict[int, str | None]) -> str:
    """The canonical deck with rows rewritten (None drops the row)."""
    out = [changes.get(r, line) for r, line in enumerate(ROWS)]
    return "\n".join(line for line in out if line is not None) + "\n"


def block(ed: Ed, header: str) -> list[str]:
    """The stripped lines of the zone block opened by a bare `header`:
    indented lines until the next unindented non-blank line
    (docs/deck-format.md, zone block headers)."""
    lines = ed.lines
    assert header in lines, f"no {header} block in:\n{ed.text}"
    out: list[str] = []
    for line in lines[lines.index(header) + 1:]:
        if line and not line[0].isspace():
            break
        if line.strip():
            out.append(line.strip())
    return out


PLUS = [
    pytest.param("+", marks=pytest.mark.primitive("visual:+"), id="plus"),
    pytest.param("<C-a>", marks=pytest.mark.primitive("visual:ctrl_a"), id="ctrl_a"),
]
MINUS = [
    pytest.param("-", marks=pytest.mark.primitive("visual:-"), id="minus"),
    pytest.param("<C-x>", marks=pytest.mark.primitive("visual:ctrl_x"), id="ctrl_x"),
]
ALL_QUANTITY = PLUS + MINUS


# -- + Ctrl-A --------------------------------------------------------------------


@pytest.mark.parametrize("key", PLUS)
async def test_increment_adds_one_to_every_selected_card(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vjj {key}")
        assert ed.text == deck_with({
            7: "    5 Goblin Guide",
            8: "    3 Eidolon of the Great Revel",
            9: "    4 Bonecrusher Giant // Stomp",
        })


@pytest.mark.parametrize("key", PLUS)
async def test_increment_with_a_count_adds_it_to_each_card(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vjj 3{key}")
        assert ed.text == deck_with({
            7: "    7 Goblin Guide",
            8: "    5 Eidolon of the Great Revel",
            9: "    6 Bonecrusher Giant // Stomp",
        })


@pytest.mark.parametrize("key", PLUS)
async def test_increment_skips_a_header_and_blank_in_the_selection(
    tmp_path: Path, key: str
) -> None:
    async with editor(tmp_path) as ed:
        # Bonecrusher, blank, // Instant, Lightning Bolt
        ed.press(f"10G Vjj {key}")
        assert ed.text == deck_with({
            9: "    4 Bonecrusher Giant // Stomp",
            12: "    5 Lightning Bolt",
        })


@pytest.mark.primitive("visual:+")
async def test_increment_with_the_section_header_selected(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("7G Vjjj +")
        assert ed.text == deck_with({
            7: "    5 Goblin Guide",
            8: "    3 Eidolon of the Great Revel",
            9: "    4 Bonecrusher Giant // Stomp",
        })


@pytest.mark.primitive("visual:+")
async def test_increment_across_the_deck_and_sideboard_keeps_the_zones(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("17G VG +")
        assert ed.text == deck_with({
            16: "    5 Sacred Foundry",
            17: "    17 Mountain",
            20: "    3 Rest in Peace",
        })


@pytest.mark.primitive("visual:+")
async def test_increment_keeps_prefixes_categories_and_comments(tmp_path: Path) -> None:
    deck = (
        "// Deck: Burn\n// Format: modern\n// Tags:\n\n"
        "4 Lightning Bolt  @removal  // core\n"
        "SB: 2 Rest in Peace\n"
    )
    async with editor(tmp_path, deck) as ed:
        ed.press("5G Vj +")
        assert ed.lines[4:6] == ["5 Lightning Bolt  @removal  // core", "SB: 3 Rest in Peace"]


@pytest.mark.primitive("visual:+")
async def test_increment_then_dot_repeats_on_as_many_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj + 13G .")
        assert ed.text == deck_with({
            7: "    5 Goblin Guide",
            8: "    3 Eidolon of the Great Revel",
            12: "    5 Lightning Bolt",
            13: "    2 Fire // Ice",
        })


# -- - Ctrl-X --------------------------------------------------------------------


@pytest.mark.parametrize("key", MINUS)
async def test_decrement_takes_one_from_every_selected_card(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vjj {key}")
        assert ed.text == deck_with({
            7: "    3 Goblin Guide",
            8: "    1 Eidolon of the Great Revel",
            9: "    2 Bonecrusher Giant // Stomp",
        })


@pytest.mark.parametrize("key", MINUS)
async def test_decrement_deletes_a_card_that_reaches_zero(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        # Lightning Bolt (4) and Fire // Ice (1)
        ed.press(f"13G Vj {key}")
        assert ed.text == deck_with({12: "    3 Lightning Bolt", 13: None})


@pytest.mark.parametrize("key", MINUS)
async def test_decrement_with_a_count_deletes_cards_it_empties(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        # 4, 2 and 3 copies, less three each
        ed.press(f"8G Vjj 3{key}")
        assert ed.text == deck_with({7: "    1 Goblin Guide", 8: None, 9: None})


@pytest.mark.primitive("visual:-")
async def test_decrement_skips_a_header_and_blank_in_the_selection(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("10G Vjj -")
        assert ed.text == deck_with({
            9: "    2 Bonecrusher Giant // Stomp",
            12: "    3 Lightning Bolt",
        })


# -- shared: cursor, mode, undo ----------------------------------------------------------


@pytest.mark.parametrize("key", ALL_QUANTITY)
async def test_quantity_key_returns_to_normal_mode(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vj {key}")
        assert ed.mode is Mode.NORMAL
        assert ed.modified is True


@pytest.mark.parametrize("key", ALL_QUANTITY)
async def test_quantity_key_leaves_the_cursor_at_the_top_of_the_selection(
    tmp_path: Path, key: str
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"10G Vkk {key}")
        assert ed.row == 7


@pytest.mark.parametrize("key", ALL_QUANTITY)
async def test_quantity_key_undoes_in_one_step(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"8G Vjj 3{key} u")
        assert ed.text == DECK


@pytest.mark.parametrize("key", MINUS)
async def test_decrement_that_deletes_undoes_in_one_step(tmp_path: Path, key: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"13G Vj {key} u")
        assert ed.text == DECK


# -- zone keys ---------------------------------------------------------------------


MAIN_TWO = ["4 Goblin Guide", "2 Eidolon of the Great Revel"]


@pytest.mark.primitive("visual:zs")
async def test_zs_moves_every_selected_card_to_the_sideboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj zs")
        assert sorted(block(ed, "SB:")) == sorted(["2 Rest in Peace", *MAIN_TWO])
        assert not set(MAIN_TWO) & set(block(ed, "DCK:"))
        assert "3 Bonecrusher Giant // Stomp" in block(ed, "DCK:")


@pytest.mark.primitive("visual:zs")
async def test_zs_message_counts_the_cards_and_names_the_zone(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj zs")
        assert re.search(r"\b2 card", ed.message), ed.message
        assert "sideboard" in ed.message
        assert ed.is_error is False


@pytest.mark.primitive("visual:zs")
async def test_zs_returns_to_normal_at_the_top_of_the_selection(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj zs")
        assert ed.mode is Mode.NORMAL
        assert ed.row == 7


@pytest.mark.primitive("visual:zs")
async def test_zs_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj zs u")
        assert ed.text == DECK


@pytest.mark.primitive("visual:zs")
async def test_zs_with_the_header_selected_moves_only_cards(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("7G Vjjj zs")
        assert sorted(block(ed, "SB:")) == sorted([
            "2 Rest in Peace", *MAIN_TWO, "3 Bonecrusher Giant // Stomp",
        ])
        assert re.search(r"\b3 card", ed.message), ed.message
        # The emptied derived header goes with its last card
        assert "    // Creature" not in ed.lines


@pytest.mark.primitive("visual:zs")
async def test_zs_with_a_count_splits_that_many_off_each_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj 1zs")
        dck = block(ed, "DCK:")
        assert "3 Goblin Guide" in dck
        assert "1 Eidolon of the Great Revel" in dck
        assert sorted(block(ed, "SB:")) == sorted([
            "2 Rest in Peace", "1 Goblin Guide", "1 Eidolon of the Great Revel",
        ])


@pytest.mark.primitive("visual:zs")
async def test_zs_on_a_selection_without_cards_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("7G V zs")
        assert ed.text == DECK
        assert ed.modified is False
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("visual:zm")
async def test_zm_moves_every_selected_card_to_a_new_maybeboard_block(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj zm")
        assert sorted(block(ed, "MB:")) == sorted(MAIN_TWO)
        assert not set(MAIN_TWO) & set(block(ed, "DCK:"))
        assert "maybeboard" in ed.message
        assert re.search(r"\b2 card", ed.message), ed.message


@pytest.mark.primitive("visual:zm")
async def test_zm_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj zm")
        assert ed.mode is Mode.NORMAL
        ed.press("u")
        assert ed.text == DECK


SIDEBOARD_TWO = (
    "// Deck: Burn\n// Format: modern\n// Tags:\n\n"
    "DCK:\n"
    "\n"
    "    // Creature\n"
    "    4 Goblin Guide\n"
    "\n"
    "    // Instant\n"
    "    4 Lightning Bolt\n"
    "\n"
    "SB:\n"
    "    2 Rest in Peace\n"
    "    2 Lightning Bolt\n"
)


@pytest.mark.primitive("visual:zd")
async def test_zd_moves_every_selected_card_into_the_main_deck(tmp_path: Path) -> None:
    async with editor(tmp_path, SIDEBOARD_TWO) as ed:
        ed.press("14G Vj zd")
        dck = block(ed, "DCK:")
        # Bolt merges into the existing line; Rest in Peace joins the deck
        assert "6 Lightning Bolt" in dck
        assert "2 Rest in Peace" in dck
        assert block(ed, "SB:") == []
        assert "main deck" in ed.message
        assert re.search(r"\b2 card", ed.message), ed.message


@pytest.mark.primitive("visual:zd")
async def test_zd_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path, SIDEBOARD_TWO) as ed:
        ed.press("14G Vj zd")
        assert ed.mode is Mode.NORMAL
        ed.press("u")
        assert ed.text == SIDEBOARD_TWO


@pytest.mark.primitive("visual:zc")
async def test_zc_is_refused_outside_a_commander_format(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj zc")
        assert ed.text == DECK
        assert ed.modified is False
        assert ed.is_error is True
        assert ed.mode is Mode.NORMAL


COMMANDER = (
    "// Deck: Big Red\n// Format: commander\n// Tags:\n\n"
    "DCK:\n"
    "\n"
    "    // Creature\n"
    "    1 Goblin Guide\n"
    "    1 Eidolon of the Great Revel\n"
    "    1 Bonecrusher Giant // Stomp\n"
)


@pytest.mark.primitive("visual:zc")
async def test_zc_moves_every_selected_card_to_the_command_zone(tmp_path: Path) -> None:
    async with editor(tmp_path, COMMANDER) as ed:
        ed.press("8G Vj zc")
        assert sorted(block(ed, "CMD:")) == sorted([
            "1 Goblin Guide", "1 Eidolon of the Great Revel",
        ])
        assert block(ed, "DCK:") == ["// Creature", "1 Bonecrusher Giant // Stomp"]
        assert "commander" in ed.message
        assert re.search(r"\b2 card", ed.message), ed.message


@pytest.mark.primitive("visual:zc")
async def test_zc_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path, COMMANDER) as ed:
        ed.press("8G Vj zc")
        assert ed.mode is Mode.NORMAL
        ed.press("u")
        assert ed.text == COMMANDER


@pytest.mark.primitive("visual:zp")
async def test_zp_moves_every_selected_card_to_the_companion_slot(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj zp")
        assert sorted(block(ed, "CMP:")) == sorted(MAIN_TWO)
        assert not set(MAIN_TWO) & set(block(ed, "DCK:"))
        assert "companion" in ed.message
        assert re.search(r"\b2 card", ed.message), ed.message


@pytest.mark.primitive("visual:zp")
async def test_zp_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj zp")
        assert ed.mode is Mode.NORMAL
        ed.press("u")
        assert ed.text == DECK


# -- plan keys -----------------------------------------------------------------------


PLANNED = DECK + "    3 Lava Spike\n"  # a second sideboard card, row 21


@pytest.mark.primitive("visual:zo")
async def test_zo_boards_every_selected_card_out_of_the_active_plan(tmp_path: Path) -> None:
    async with editor(tmp_path, PLANNED) as ed:
        ed.press(":plan<Space>Tron<CR> 8G Vj zo")
        assert block(ed, "VS: Tron") == ["-4 Goblin Guide", "-2 Eidolon of the Great Revel"]
        assert "Tron" in ed.message
        assert re.search(r"\b2 card", ed.message), ed.message


@pytest.mark.primitive("visual:zo")
async def test_zo_leaves_the_deck_cards_where_they_are(tmp_path: Path) -> None:
    async with editor(tmp_path, PLANNED) as ed:
        ed.press(":plan<Space>Tron<CR> 8G Vj zo")
        assert ed.lines[:22] == PLANNED.splitlines()
        assert ed.mode is Mode.NORMAL
        assert ed.row == 7


@pytest.mark.primitive("visual:zo")
async def test_zo_with_the_header_selected_boards_only_cards(tmp_path: Path) -> None:
    async with editor(tmp_path, PLANNED) as ed:
        ed.press(":plan<Space>Tron<CR> 7G Vjjj zo")
        assert block(ed, "VS: Tron") == [
            "-4 Goblin Guide", "-2 Eidolon of the Great Revel", "-3 Bonecrusher Giant // Stomp",
        ]


@pytest.mark.primitive("visual:zo")
async def test_zo_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path, PLANNED) as ed:
        ed.press(":plan<Space>Tron<CR>")
        before = ed.text
        ed.press("8G Vj zo u")
        assert ed.text == before


@pytest.mark.primitive("visual:zo")
async def test_zo_without_a_plan_is_refused(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj zo")
        assert ed.text == DECK
        assert ed.is_error is True
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("visual:zi")
async def test_zi_boards_every_selected_card_into_the_active_plan(tmp_path: Path) -> None:
    async with editor(tmp_path, PLANNED) as ed:
        ed.press(":plan<Space>Tron<CR> 21G Vj zi")
        assert block(ed, "VS: Tron") == ["+2 Rest in Peace", "+3 Lava Spike"]
        assert "Tron" in ed.message
        assert re.search(r"\b2 card", ed.message), ed.message
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("visual:zi")
async def test_zi_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path, PLANNED) as ed:
        ed.press(":plan<Space>Tron<CR>")
        before = ed.text
        ed.press("21G Vj zi u")
        assert ed.text == before


@pytest.mark.primitive("visual:zi")
async def test_zi_without_a_plan_is_refused(tmp_path: Path) -> None:
    async with editor(tmp_path, PLANNED) as ed:
        ed.press("21G Vj zi")
        assert ed.text == PLANNED
        assert ed.is_error is True
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("visual:zc")
@pytest.mark.xfail(
    strict=True,
    reason="BUG: visual zc of non-legendary cards should say why they can't lead the deck "
    "(as zc does); it says only 'Moved 2 card(s) to commander'",
)
async def test_zc_says_why_a_selected_card_cannot_be_commander(tmp_path: Path) -> None:
    async with editor(tmp_path, COMMANDER) as ed:
        ed.press("8G Vj zc")
        assert "not legendary" in ed.message


@pytest.mark.primitive("visual:zs")
async def test_zs_in_a_format_without_a_sideboard_moves_and_warns(tmp_path: Path) -> None:
    async with editor(tmp_path, COMMANDER) as ed:
        ed.press("8G Vj zs")
        assert sorted(block(ed, "SB:")) == sorted([
            "1 Goblin Guide", "1 Eidolon of the Great Revel",
        ])
        assert "warning" in ed.message


@pytest.mark.primitive("visual:+")
async def test_two_visual_increments_undo_one_at_a_time(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G Vj + 13G Vj + u")
        assert ed.text == deck_with({
            7: "    5 Goblin Guide",
            8: "    3 Eidolon of the Great Revel",
        })


@pytest.mark.primitive("visual:+")
async def test_increment_on_a_selection_without_cards_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("7G V +")
        assert ed.text == DECK
        assert ed.modified is False
        assert ed.mode is Mode.NORMAL


@pytest.mark.primitive("visual:-")
async def test_decrement_that_empties_a_section_drops_its_header(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("13G Vj 4-")
        assert "4 Lightning Bolt" not in ed.cards
        assert "1 Fire // Ice" not in ed.cards
        assert "    // Instant" not in ed.lines


@pytest.mark.primitive("visual:-")
async def test_decrement_that_empties_a_section_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("13G Vj 4- u")
        assert ed.text == DECK


@pytest.mark.primitive("visual:zs")
async def test_zs_that_empties_a_section_undoes_in_one_step(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("7G Vjjj zs u")
        assert ed.text == DECK

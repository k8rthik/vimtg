"""Navigation motions (j k gg G w b { } [[ ]]), driven through real keys.

Expected rows come from docs/keybindings.md (the Navigation table and the
jumplist rules) and, where it is silent, from vim adapted to card lines.
Row numbers refer to the canonical DECK map in the harness. Every case
also checks that moving the cursor never edits the deck.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, Ed, editor

pytestmark = pytest.mark.asyncio

# Canonical deck rows (see the map in harness.py)
META_DECK, META_FORMAT, META_TAGS, DCK_ROW = 0, 1, 2, 4
CREATURE_HDR, GOBLIN, EIDOLON, BONECRUSHER = 6, 7, 8, 9
INSTANT_HDR, BOLT, FIRE_ICE = 11, 12, 13
LAND_HDR, FOUNDRY, MOUNTAIN = 15, 16, 17
SB_ROW, RIP = 19, 20
LAST = RIP
NON_BLANK = (0, 1, 2, 4, 6, 7, 8, 9, 11, 12, 13, 15, 16, 17, 19, 20)
CARD_ROWS = (GOBLIN, EIDOLON, BONECRUSHER, BOLT, FIRE_ICE, FOUNDRY, MOUNTAIN, RIP)

# A deck with no card lines at all
EMPTY_DECK = "// Deck: Empty\n// Format: modern\n// Tags:\n\nDCK:\n"

# The canonical deck with one sideboard plan after the zones
PLAN_DECK = DECK + "\nVS: Tron\n    -4 Lightning Bolt\n    +2 Rest in Peace\n"
PLAN_HDR, PLAN_OUT, PLAN_IN = 22, 23, 24


def tall_deck(lines: int) -> str:
    """A deck of exactly `lines` lines: four metadata rows, DCK:, then
    one-copy fillers, so row r (r >= 5) is 'Filler {r - 4:03d}'."""
    head = ["// Deck: Tall", "// Format: modern", "// Tags:", "", "DCK:"]
    body = [f"    1 Filler {i:03d}" for i in range(1, lines - len(head) + 1)]
    return "\n".join(head + body) + "\n"


def unchanged(ed: Ed, text: str = DECK) -> None:
    """Navigation never edits: the buffer is as opened and not modified."""
    assert ed.text == text
    assert ed.modified is False


def goto(ed: Ed, row: int) -> None:
    """Put the cursor on `row` with j only, so no jump is recorded."""
    ed.press(f"{NON_BLANK.index(row)}j" if row else "")
    assert ed.row == row


# ── j / k ────────────────────────────────────────────────────────────


@pytest.mark.primitive("j")
async def test_j_moves_down_one_line_from_a_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("j")
        assert ed.row == EIDOLON
        unchanged(ed)


@pytest.mark.primitive("j")
async def test_j_skips_a_blank_line_onto_the_next_header(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, BONECRUSHER)
        ed.press("j")
        assert ed.row == INSTANT_HDR
        unchanged(ed)


@pytest.mark.primitive("j")
async def test_j_walks_metadata_rows_and_stops_on_the_dck_marker(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("j")
        assert ed.row == META_FORMAT
        ed.press("j j")
        assert ed.row == DCK_ROW
        unchanged(ed)


@pytest.mark.primitive("j")
async def test_j_stops_on_the_sb_marker_before_the_sideboard_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, MOUNTAIN)
        ed.press("j")
        assert ed.row == SB_ROW
        ed.press("j")
        assert ed.row == RIP
        unchanged(ed)


@pytest.mark.primitive("j")
async def test_count_j_counts_only_non_blank_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("3j")  # Eidolon, Bonecrusher, (blank skipped) // Instant
        assert ed.row == INSTANT_HDR
        unchanged(ed)


@pytest.mark.primitive("j")
async def test_count_j_past_the_end_stops_on_the_last_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("100j")
        assert ed.row == LAST
        unchanged(ed)


@pytest.mark.primitive("j")
async def test_j_on_the_last_line_stays(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G j")
        assert ed.row == LAST
        unchanged(ed)


@pytest.mark.primitive("j")
async def test_j_from_a_blank_line_lands_on_the_next_non_blank(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("4G")  # row 3, the blank after the metadata
        assert ed.lines[ed.row] == ""
        ed.press("j")
        assert ed.row == DCK_ROW
        unchanged(ed)


@pytest.mark.primitive("k")
async def test_k_moves_up_one_line_from_a_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FIRE_ICE)
        ed.press("k")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("k")
async def test_k_skips_a_blank_line_onto_the_card_above(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, INSTANT_HDR)
        ed.press("k")
        assert ed.row == BONECRUSHER
        unchanged(ed)


@pytest.mark.primitive("k")
async def test_k_from_the_sideboard_card_lands_on_the_sb_marker(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G k")
        assert ed.row == SB_ROW
        unchanged(ed)


@pytest.mark.primitive("k")
async def test_k_from_the_dck_marker_skips_the_blank_onto_metadata(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, DCK_ROW)
        ed.press("k")
        assert ed.row == META_TAGS
        unchanged(ed)


@pytest.mark.primitive("k")
async def test_count_k_counts_only_non_blank_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FOUNDRY)
        ed.press("4k")  # // Land, Fire // Ice, Bolt, // Instant
        assert ed.row == INSTANT_HDR
        unchanged(ed)


@pytest.mark.primitive("k")
async def test_count_k_past_the_top_stops_on_the_first_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G 100k")
        assert ed.row == 0
        unchanged(ed)


@pytest.mark.primitive("k")
async def test_k_on_the_first_line_stays(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("k")
        assert ed.row == 0
        unchanged(ed)


@pytest.mark.primitive("k")
async def test_k_from_a_blank_line_lands_on_the_previous_non_blank(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("11G")  # row 10, the blank after the creatures
        assert ed.lines[ed.row] == ""
        ed.press("k")
        assert ed.row == BONECRUSHER
        unchanged(ed)


# ── gg / G ───────────────────────────────────────────────────────────


@pytest.mark.primitive("gg")
async def test_gg_goes_to_the_first_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FIRE_ICE)
        ed.press("gg")
        assert ed.row == 0
        unchanged(ed)


@pytest.mark.primitive("gg")
async def test_count_gg_goes_to_that_line_number(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("13gg")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("gg")
async def test_count_gg_past_the_end_goes_to_the_last_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("99gg")
        assert ed.row == LAST
        unchanged(ed)


@pytest.mark.primitive("G")
async def test_big_g_goes_to_the_last_line_the_sideboard_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("G")
        assert ed.row == LAST
        assert ed.line == "2 Rest in Peace"
        unchanged(ed)


@pytest.mark.primitive("G")
async def test_count_big_g_goes_to_that_line_number(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G")
        assert ed.line == "4 Goblin Guide"
        ed.press("5G")
        assert ed.row == DCK_ROW
        unchanged(ed)


@pytest.mark.primitive("G")
async def test_count_big_g_of_one_is_the_first_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G 1G")
        assert ed.row == 0
        unchanged(ed)


@pytest.mark.primitive("G")
async def test_count_big_g_past_the_end_goes_to_the_last_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("22G")
        assert ed.row == LAST
        ed.press("gg 500G")
        assert ed.row == LAST
        unchanged(ed)


@pytest.mark.primitive("G")
async def test_count_big_g_lands_on_a_section_header_and_the_sb_marker(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("12G")
        assert ed.line == "// Instant"
        ed.press("20G")
        assert ed.line == "SB:"
        unchanged(ed)


# ── w / b ────────────────────────────────────────────────────────────


@pytest.mark.primitive("w")
async def test_w_moves_to_the_next_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("w")
        assert ed.row == EIDOLON
        unchanged(ed)


@pytest.mark.primitive("w")
async def test_w_skips_blank_and_header_into_the_next_section(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, BONECRUSHER)
        ed.press("w")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("w")
async def test_w_from_metadata_skips_to_the_first_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("w")
        assert ed.row == GOBLIN
        unchanged(ed)


@pytest.mark.primitive("w")
async def test_w_crosses_the_sb_marker_into_the_sideboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, MOUNTAIN)
        ed.press("w")
        assert ed.row == RIP
        unchanged(ed)


@pytest.mark.primitive("w")
async def test_w_lands_only_on_card_lines(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        visited = []
        for _ in range(len(CARD_ROWS)):
            ed.press("w")
            visited.append(ed.row)
        assert visited == list(CARD_ROWS)
        unchanged(ed)


@pytest.mark.primitive("w")
async def test_count_w_moves_that_many_cards(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("3w")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("w")
async def test_count_w_past_the_last_card_stops_on_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("50w")
        assert ed.row == RIP
        unchanged(ed)


@pytest.mark.primitive("w")
async def test_w_on_the_last_card_stays(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G w")
        assert ed.row == RIP
        unchanged(ed)


@pytest.mark.primitive("b")
async def test_b_moves_to_the_previous_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FIRE_ICE)
        ed.press("b")
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("b")
async def test_b_skips_header_and_blank_into_the_previous_section(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, BOLT)
        ed.press("b")
        assert ed.row == BONECRUSHER
        unchanged(ed)


@pytest.mark.primitive("b")
async def test_b_from_the_sideboard_crosses_the_sb_marker(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G b")
        assert ed.row == MOUNTAIN
        unchanged(ed)


@pytest.mark.primitive("b")
async def test_b_from_a_header_lands_on_the_card_above(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, LAND_HDR)
        ed.press("b")
        assert ed.row == FIRE_ICE
        unchanged(ed)


@pytest.mark.primitive("b")
async def test_count_b_moves_that_many_cards(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G 4b")  # Mountain, Foundry, Fire // Ice, Bolt
        assert ed.row == BOLT
        unchanged(ed)


@pytest.mark.primitive("b")
async def test_b_on_the_first_card_stays(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("b")
        assert ed.row == GOBLIN
        ed.press("G 50b")
        assert ed.row == GOBLIN
        unchanged(ed)


# ── { / } ────────────────────────────────────────────────────────────
# "Previous / next section": the cursor lands at the start of the
# section, on its header or its first card.


@pytest.mark.primitive("}")
async def test_close_brace_moves_to_the_next_section(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, EIDOLON)
        ed.press("}")
        assert ed.row in (INSTANT_HDR, BOLT)
        unchanged(ed)


@pytest.mark.primitive("}")
@pytest.mark.xfail(strict=True, reason=(
    "BUG: } on the // Instant header should move to the next section (// Land, "
    "row 15 or 16); it stops on Lightning Bolt (row 12), inside the header's own section"
))
async def test_close_brace_from_a_header_moves_past_its_section(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, INSTANT_HDR)
        ed.press("}")
        assert ed.row in (LAND_HDR, FOUNDRY)
        unchanged(ed)


@pytest.mark.primitive("}")
async def test_count_close_brace_skips_that_many_sections(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("2}")
        assert ed.row in (LAND_HDR, FOUNDRY)
        unchanged(ed)


@pytest.mark.primitive("}")
async def test_close_brace_from_the_last_main_section_reaches_the_sideboard(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FOUNDRY)
        ed.press("}")
        assert ed.row in (SB_ROW, RIP)
        unchanged(ed)


@pytest.mark.primitive("}")
async def test_close_brace_past_the_last_section_goes_to_the_last_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("9}")
        assert ed.row == LAST
        ed.press("}")
        assert ed.row == LAST
        unchanged(ed)


@pytest.mark.primitive("{")
async def test_open_brace_moves_to_the_previous_section(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FOUNDRY)
        ed.press("{")
        assert ed.row in (INSTANT_HDR, BOLT)
        unchanged(ed)


@pytest.mark.primitive("{")
async def test_open_brace_from_mid_section_moves_to_the_previous_section(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FIRE_ICE)
        ed.press("{")
        assert ed.row in (CREATURE_HDR, GOBLIN)
        unchanged(ed)


@pytest.mark.primitive("{")
async def test_count_open_brace_skips_that_many_sections(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, MOUNTAIN)
        ed.press("2{")
        assert ed.row in (CREATURE_HDR, GOBLIN)
        unchanged(ed)


@pytest.mark.primitive("{")
async def test_open_brace_from_the_sideboard_returns_to_the_main_deck(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G {")
        assert ed.row in (LAND_HDR, FOUNDRY)
        unchanged(ed)


@pytest.mark.primitive("{")
async def test_open_brace_before_the_first_section_goes_to_the_first_line(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("{")
        assert ed.row == 0
        ed.press("G 9{")
        assert ed.row == 0
        unchanged(ed)


# ── [[ / ]] ──────────────────────────────────────────────────────────


@pytest.mark.primitive("]]")
async def test_close_brackets_moves_to_the_next_section_header(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("]]")
        assert ed.row == INSTANT_HDR
        assert ed.line == "// Instant"
        unchanged(ed)


@pytest.mark.primitive("]]")
async def test_close_brackets_from_a_header_moves_to_the_next_one(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, INSTANT_HDR)
        ed.press("]]")
        assert ed.row == LAND_HDR
        unchanged(ed)


@pytest.mark.primitive("]]")
async def test_count_close_brackets_skips_that_many_headers(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("2]]")
        assert ed.row == LAND_HDR
        unchanged(ed)


@pytest.mark.primitive("]]")
async def test_close_brackets_past_the_last_header_goes_to_the_last_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, GOBLIN)
        ed.press("9]]")
        assert ed.row == LAST
        unchanged(ed)


@pytest.mark.primitive("]]")
async def test_close_brackets_from_metadata_skips_the_dck_marker(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("]]")
        assert ed.row == CREATURE_HDR
        unchanged(ed)


@pytest.mark.primitive("]]")
async def test_close_brackets_stops_on_a_plan_header(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        opened = ed.text
        ed.press("G")
        assert ed.row == PLAN_IN
        ed.press("gg 21G ]]")  # from Rest in Peace
        assert ed.row == PLAN_HDR
        assert ed.line == "VS: Tron"
        unchanged(ed, opened)


@pytest.mark.primitive("[[")
async def test_open_brackets_moves_to_the_header_of_this_section(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FIRE_ICE)
        ed.press("[[")
        assert ed.row == INSTANT_HDR
        unchanged(ed)


@pytest.mark.primitive("[[")
async def test_open_brackets_from_a_header_moves_to_the_previous_one(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, LAND_HDR)
        ed.press("[[")
        assert ed.row == INSTANT_HDR
        unchanged(ed)


@pytest.mark.primitive("[[")
async def test_count_open_brackets_skips_that_many_headers(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, FOUNDRY)
        ed.press("2[[")
        assert ed.row == INSTANT_HDR
        unchanged(ed)


@pytest.mark.primitive("[[")
async def test_open_brackets_before_the_first_header_goes_to_the_first_line(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        goto(ed, MOUNTAIN)
        ed.press("9[[")
        assert ed.row == 0
        ed.press("[[")
        assert ed.row == 0
        unchanged(ed)


@pytest.mark.primitive("[[")
async def test_open_brackets_from_the_sideboard_skips_the_sb_marker(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("G [[")
        assert ed.row == LAND_HDR
        unchanged(ed)


@pytest.mark.primitive("[[")
async def test_open_brackets_from_a_plan_entry_reaches_its_plan_header(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        opened = ed.text
        ed.press("G [[")
        assert ed.row == PLAN_HDR
        unchanged(ed, opened)

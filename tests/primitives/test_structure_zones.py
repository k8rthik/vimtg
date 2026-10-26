"""Zone moves: zs zm zd zc zp.

Spec: docs/keybindings.md "Zones", docs/deck-format.md "Other zones" and
"Zone block headers", README "Zones" and "Sections, layouts, and placement".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, editor
from tests.primitives.test_structure_support import (
    BOLT_ROW,
    CAT_DECK,
    CMD_DECK,
    GOBLIN_ROW,
    MB_DECK,
    PREFIX_DECK,
    RIP_ROW,
    card_row,
    entry,
    header_above,
    zone,
)

pytestmark = pytest.mark.asyncio

G_GOBLIN = f"{GOBLIN_ROW + 1}G"

# DECK with Goblin Guide in the sideboard as well (row 20), so a move in
# either direction lands on a line that already holds the card.
MERGE_DECK = DECK.replace(
    "SB:\n    2 Rest in Peace\n", "SB:\n    1 Goblin Guide\n    2 Rest in Peace\n"
)
# DECK with a sideboard creature the mainboard lacks (row 21).
DELVER_DECK = DECK + "    1 Delver of Secrets // Insectile Aberration\n"
# DECK whose Lightning Bolt carries a category, a tag and a comment.
TOKENS_DECK = DECK.replace(
    "    4 Lightning Bolt\n", "    4 Lightning Bolt  @burn  #core  // best\n"
)
# The category deck with a categorized sideboard card (row 19).
CAT_SB_DECK = CAT_DECK + "    1 Fire // Ice  @burn\n"


# --- zs -------------------------------------------------------------------


@pytest.mark.primitive("zs")
async def test_zs_moves_every_copy_to_the_sideboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} zs")
        assert "Goblin Guide" not in zone(ed.text, "main")
        assert zone(ed.text, "side") == {"Goblin Guide": 4, "Rest in Peace": 2}
        assert ed.message == "Moved 4x Goblin Guide to sideboard"
        assert ed.modified


@pytest.mark.primitive("zs")
async def test_zs_with_a_count_splits_the_stack_and_names_the_remainder(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} 2zs")
        assert zone(ed.text, "main")["Goblin Guide"] == 2
        assert zone(ed.text, "side") == {"Goblin Guide": 2, "Rest in Peace": 2}
        assert ed.message == "Moved 2x Goblin Guide to sideboard (2 remain)"


@pytest.mark.primitive("zs")
async def test_zs_with_a_count_above_the_stack_moves_every_copy(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} 9zs")
        assert "Goblin Guide" not in zone(ed.text, "main")
        assert zone(ed.text, "side")["Goblin Guide"] == 4


@pytest.mark.primitive("zs")
async def test_zs_merges_into_the_sideboard_line_already_holding_the_card(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, MERGE_DECK) as ed:
        ed.press(f"{G_GOBLIN} 2zs")
        assert zone(ed.text, "side")["Goblin Guide"] == 3
        sb = ed.lines[ed.lines.index("SB:"):]
        assert sum("Goblin Guide" in line for line in sb) == 1


@pytest.mark.primitive("zs")
async def test_zs_writes_an_indented_line_inside_the_sideboard_block(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} zs")
        row = card_row(ed.lines, "Goblin Guide")
        assert ed.lines[row] == "    4 Goblin Guide"
        assert header_above(ed.lines, "Goblin Guide") == "SB:"


@pytest.mark.primitive("zs")
async def test_zs_writes_a_prefixed_line_next_to_prefix_style_sideboard(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, PREFIX_DECK) as ed:
        assert ed.text == PREFIX_DECK
        ed.press("6G zs")
        assert "SB: 4 Goblin Guide" in ed.lines
        assert "DCK:" not in ed.lines and "SB:" not in ed.lines


@pytest.mark.primitive("zs")
async def test_zs_keeps_the_category_tags_and_comment(tmp_path: Path) -> None:
    async with editor(tmp_path, TOKENS_DECK) as ed:
        ed.press(f"{BOLT_ROW + 1}G zs")
        moved = entry(ed.text, "Lightning Bolt", "side")
        assert (moved.quantity, moved.category, moved.tags, moved.comment) == (
            4, "burn", frozenset({"core"}), "best",
        )


@pytest.mark.primitive("zs")
async def test_zs_split_keeps_the_tokens_on_both_halves(tmp_path: Path) -> None:
    async with editor(tmp_path, TOKENS_DECK) as ed:
        ed.press(f"{BOLT_ROW + 1}G 1zs")
        for zone_name, qty in (("main", 3), ("side", 1)):
            e = entry(ed.text, "Lightning Bolt", zone_name)
            assert (e.quantity, e.category, e.tags, e.comment) == (
                qty, "burn", frozenset({"core"}), "best",
            )


@pytest.mark.primitive("zs")
async def test_zs_takes_the_cursor_with_the_card(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} zs")
        assert ed.line == "4 Goblin Guide"
        assert ed.row > ed.lines.index("SB:")


@pytest.mark.primitive("zs")
async def test_zs_on_a_card_already_in_the_sideboard_changes_nothing(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{RIP_ROW + 1}G zs")
        assert ed.text == DECK
        assert not ed.modified


@pytest.mark.primitive("zs")
async def test_zs_in_commander_moves_the_card_but_warns(tmp_path: Path) -> None:
    async with editor(tmp_path, CMD_DECK) as ed:
        ed.press("11G zs")
        assert zone(ed.text, "side") == {"Eidolon of the Great Revel": 1}
        assert "warning" in ed.message and "sideboard" in ed.message
        assert not ed.is_error


# --- zm -------------------------------------------------------------------


@pytest.mark.primitive("zm")
async def test_zm_opens_a_new_maybeboard_as_an_indented_block(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} zm")
        assert zone(ed.text, "maybe") == {"Goblin Guide": 4}
        assert "Goblin Guide" not in zone(ed.text, "main")
        mb = ed.lines.index("MB:")
        assert ed.lines[mb + 1] == "    4 Goblin Guide"
        assert ed.message == "Moved 4x Goblin Guide to maybeboard"


@pytest.mark.primitive("zm")
async def test_zm_joins_the_existing_maybeboard_block(tmp_path: Path) -> None:
    async with editor(tmp_path, MB_DECK) as ed:
        assert ed.text == MB_DECK
        ed.press("9G zm")
        assert zone(ed.text, "maybe") == {"Lava Spike": 1, "Lightning Bolt": 4}
        assert ed.lines.count("MB:") == 1
        assert header_above(ed.lines, "Lightning Bolt") == "MB:"


@pytest.mark.primitive("zm")
async def test_zm_with_a_count_leaves_the_remainder(tmp_path: Path) -> None:
    async with editor(tmp_path, MB_DECK) as ed:
        ed.press("9G 3zm")
        assert zone(ed.text, "main")["Lightning Bolt"] == 1
        assert zone(ed.text, "maybe")["Lightning Bolt"] == 3
        assert ed.message == "Moved 3x Lightning Bolt to maybeboard (1 remain)"


@pytest.mark.primitive("zm")
async def test_zm_writes_a_prefixed_line_next_to_prefix_style_maybeboard(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, PREFIX_DECK) as ed:
        ed.press("9G zm")
        assert "MB: 4 Lightning Bolt" in ed.lines
        assert "MB:" not in ed.lines


# --- zd -------------------------------------------------------------------


@pytest.mark.primitive("zd")
async def test_zd_moves_a_sideboard_card_into_the_mainboard(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{RIP_ROW + 1}G zd")
        assert zone(ed.text, "main")["Rest in Peace"] == 2
        assert zone(ed.text, "side") == {}
        assert ed.message == "Moved 2x Rest in Peace to main deck"


@pytest.mark.primitive("zd")
async def test_zd_files_a_new_type_under_a_new_plural_header_in_the_block(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{RIP_ROW + 1}G zd")
        assert header_above(ed.lines, "Rest in Peace") == "// Enchantments"
        row = card_row(ed.lines, "Rest in Peace")
        assert ed.lines[row] == "    2 Rest in Peace"
        assert row < ed.lines.index("SB:")


@pytest.mark.primitive("zd")
async def test_zd_files_the_card_under_its_existing_type_header(tmp_path: Path) -> None:
    async with editor(tmp_path, DELVER_DECK) as ed:
        ed.press("22G zd")
        assert header_above(ed.lines, "Delver of Secrets // Insectile Aberration") == (
            "// Creature"
        )
        assert ed.lines.count("    // Creature") == 1


@pytest.mark.primitive("zd")
async def test_zd_in_a_category_deck_lands_in_the_cards_own_category(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, CAT_SB_DECK) as ed:
        ed.press("20G zd")
        assert header_above(ed.lines, "Fire // Ice") == "// @burn"
        assert entry(ed.text, "Fire // Ice").category == "burn"


@pytest.mark.primitive("zd")
async def test_zd_merges_into_the_mainboard_line_already_holding_the_card(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, MERGE_DECK) as ed:
        ed.press("21G zd")
        assert zone(ed.text, "main")["Goblin Guide"] == 5
        assert "Goblin Guide" not in zone(ed.text, "side")
        assert sum("Goblin Guide" in line for line in ed.lines) == 1


@pytest.mark.primitive("zd")
async def test_zd_on_a_mainboard_card_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} zd")
        assert ed.text == DECK
        assert not ed.modified


@pytest.mark.primitive("zd")
async def test_zd_moves_the_commander_back_into_the_deck(tmp_path: Path) -> None:
    async with editor(tmp_path, CMD_DECK) as ed:
        ed.press("6G zd")
        assert zone(ed.text, "commander") == {}
        assert zone(ed.text, "main")["Goblin Guide"] == 1
        assert header_above(ed.lines, "Goblin Guide") == "// Creature"
        assert "CMD:" in ed.lines  # bare zone headers are structural


# --- zc -------------------------------------------------------------------


@pytest.mark.primitive("zc")
async def test_zc_in_commander_adds_a_partner_and_says_why_it_cannot_lead(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, CMD_DECK) as ed:
        ed.press("11G zc")
        assert zone(ed.text, "commander") == {
            "Goblin Guide": 1, "Eidolon of the Great Revel": 1,
        }
        assert header_above(ed.lines, "Eidolon of the Great Revel") == "CMD:"
        assert (
            "Eidolon of the Great Revel is not legendary and can't be your commander"
            in ed.message
        )
        assert not ed.is_error


@pytest.mark.primitive("zc")
async def test_zc_is_refused_in_a_constructed_format(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} zc")
        assert ed.text == DECK
        assert ed.is_error
        assert "command zone" in ed.message
        assert not ed.modified


@pytest.mark.primitive("zc")
async def test_zc_in_an_unknown_format_checks_nothing(tmp_path: Path) -> None:
    text = DECK.replace("// Format: modern", "// Format: kitchen-table")
    async with editor(tmp_path, text) as ed:
        ed.press(f"{G_GOBLIN} zc")
        assert zone(ed.text, "commander") == {"Goblin Guide": 4}
        assert not ed.is_error


@pytest.mark.primitive("zc")
async def test_zc_on_the_commander_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path, CMD_DECK) as ed:
        ed.press("6G zc")
        assert ed.text == CMD_DECK
        assert not ed.modified


# --- zp -------------------------------------------------------------------


@pytest.mark.primitive("zp")
async def test_zp_moves_the_card_into_the_companion_block(tmp_path: Path) -> None:
    async with editor(tmp_path, MB_DECK) as ed:
        ed.press("12G zp")
        assert zone(ed.text, "companion") == {"Lava Spike": 1}
        assert zone(ed.text, "maybe") == {}
        assert header_above(ed.lines, "Lava Spike") == "CMP:"
        assert ed.message == "Moved 1x Lava Spike to companion"


@pytest.mark.primitive("zp")
async def test_zp_opens_a_new_companion_block(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{RIP_ROW + 1}G zp")
        assert zone(ed.text, "companion") == {"Rest in Peace": 2}
        cmp_row = ed.lines.index("CMP:")
        assert ed.lines[cmp_row + 1] == "    2 Rest in Peace"


# --- every zone key -------------------------------------------------------

ZONE_KEYS = ("zs", "zm", "zd", "zp")


@pytest.mark.primitive("zs", "zm", "zd", "zc", "zp")
@pytest.mark.parametrize("key", ZONE_KEYS)
@pytest.mark.parametrize(
    "row", [0, 3, 4, 6], ids=["metadata", "blank", "zone-header", "section-header"]
)
async def test_zone_move_from_a_non_card_line_is_refused(
    tmp_path: Path, key: str, row: int
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{row + 1}G {key}")
        assert ed.text == DECK
        assert ed.is_error
        assert not ed.modified


@pytest.mark.primitive("zc")
@pytest.mark.parametrize("row", [4, 6, 9], ids=["zone-header", "blank", "section-header"])
async def test_zc_from_a_non_card_line_is_refused(tmp_path: Path, row: int) -> None:
    async with editor(tmp_path, CMD_DECK) as ed:
        ed.press(f"{row + 1}G zc")
        assert ed.text == CMD_DECK
        assert ed.is_error


UNDO_CASES = [
    (DECK, f"{G_GOBLIN} zs"),
    (DECK, f"{G_GOBLIN} 2zs"),
    (MERGE_DECK, f"{G_GOBLIN} 2zs"),
    (DECK, f"{G_GOBLIN} zm"),
    (DECK, f"{RIP_ROW + 1}G zd"),
    (MERGE_DECK, "21G zd"),
    (CMD_DECK, "11G zc"),
    (MB_DECK, "12G zp"),
]


@pytest.mark.primitive("zs", "zm", "zd", "zc", "zp")
@pytest.mark.parametrize(
    ("text", "keys"), UNDO_CASES,
    ids=["zs", "2zs", "zs-merge", "zm", "zd", "zd-merge", "zc", "zp"],
)
async def test_one_undo_restores_the_text_before_a_zone_move(
    tmp_path: Path, text: str, keys: str
) -> None:
    async with editor(tmp_path, text) as ed:
        ed.press(keys)
        assert ed.text != text
        ed.press("u")
        assert ed.text == text
        assert not ed.modified

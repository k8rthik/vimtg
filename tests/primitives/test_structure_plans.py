"""Sideboard plans: :plan :plans [v ]v zo zi.

Spec: docs/deck-format.md "Sideboard plans", docs/commands.md "Sideboard
plans", docs/keybindings.md "Zones", README "Sideboard plans".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, editor
from tests.primitives.structure_support import (
    BOLT_ROW,
    CONTROL_ROW,
    FIRE_ICE_ROW,
    GOBLIN_ROW,
    ONE_PLAN_DECK,
    PLAN_DECK,
    RIP_ROW,
    TRON_ROW,
    plan,
    plan_names,
    rendered_rows,
    status,
)

pytestmark = pytest.mark.asyncio

G_BOLT = f"{BOLT_ROW + 1}G"
G_GOBLIN = f"{GOBLIN_ROW + 1}G"
G_RIP = f"{RIP_ROW + 1}G"
TRON = ":plan<Space>Tron<CR>"
CONTROL = ":plan<Space>Control<CR>"
TRON_BEFORE = {"Lightning Bolt": -2, "Rest in Peace": 2}


def _row_of(ed_rows: list[str], card: str) -> str:
    return next(r for r in ed_rows if card in r and "VS:" not in r)


# --- :plan ----------------------------------------------------------------


@pytest.mark.primitive(":plan")
async def test_plan_activates_an_existing_plan_on_its_header(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(TRON)
        assert ed.row == TRON_ROW
        assert "vs Tron -2/+2" in status(ed)
        assert ed.text == PLAN_DECK
        assert not ed.modified


@pytest.mark.primitive(":plan")
async def test_active_plan_shows_each_deck_cards_delta(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(TRON)
        rows = rendered_rows(ed)
        assert _row_of(rows, "Lightning Bolt").rstrip().endswith("-2")
        assert _row_of(rows, "Rest in Peace").rstrip().endswith("+2")


@pytest.mark.primitive(":plan")
async def test_plan_marks_an_unbalanced_plan_in_the_status_line(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(CONTROL)
        assert "vs Control -1/+0 !" in status(ed)


@pytest.mark.primitive(":plan")
async def test_plan_with_a_new_matchup_appends_its_block_after_the_plans(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(":plan<Space>Burn<Space>(draw)<CR>")
        assert plan_names(ed.text) == ["Tron", "Control", "Burn (draw)"]
        assert ed.text.rstrip("\n").endswith("\nVS: Burn (draw)")
        assert ed.line == "VS: Burn (draw)"
        assert "vs Burn (draw)" in status(ed)
        assert ed.modified


@pytest.mark.primitive(":plan")
async def test_plan_in_a_deck_without_plans_puts_the_block_after_the_zones(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(TRON)
        assert ed.text.startswith(DECK.rstrip("\n"))
        assert ed.text.rstrip("\n").endswith("\nVS: Tron")
        assert plan_names(ed.text) == ["Tron"]


@pytest.mark.primitive(":plan")
async def test_bare_plan_activates_the_next_plan_and_wraps(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        seen = []
        for _ in range(3):
            ed.press(":plan<CR>")
            seen.append(ed.row)
        assert seen == [TRON_ROW, CONTROL_ROW, TRON_ROW]
        assert "vs Tron" in status(ed)


@pytest.mark.primitive(":plan")
async def test_bare_plan_without_any_plan_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":plan<CR>")
        assert ed.is_error
        assert ed.text == DECK


@pytest.mark.primitive(":plan")
async def test_plan_bang_deactivates(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{TRON} :plan!<CR>")
        assert "vs Tron" not in status(ed)
        assert "-2" not in _row_of(rendered_rows(ed), "Lightning Bolt")
        ed.press(f"{G_BOLT} zo")  # no plan to board into any more
        assert ed.is_error
        assert ed.text == PLAN_DECK


@pytest.mark.primitive(":plan")
async def test_one_undo_removes_a_new_plan_block(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(":plan<Space>Burn<CR>")
        assert ed.text != PLAN_DECK
        ed.press("u")
        assert ed.text == PLAN_DECK
        assert not ed.modified


# --- :plans ---------------------------------------------------------------


@pytest.mark.primitive(":plans")
async def test_plans_lists_every_plan_with_its_totals(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(":plans<CR>")
        msg = ed.message
        assert "Tron" in msg and "Control" in msg
        assert msg.index("Tron") < msg.index("Control")
        tron = msg[msg.index("Tron"):msg.index("Control")]
        assert "-2" in tron and "+2" in tron
        assert "-1" in msg[msg.index("Control"):]
        assert "*" not in msg
        assert ed.text == PLAN_DECK


@pytest.mark.primitive(":plans")
async def test_plans_stars_the_active_plan(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{CONTROL} :plans<CR>")
        msg = ed.message
        assert msg.count("*") == 1
        assert msg.index("*") > msg.index("Tron")
        assert msg.index("*") < msg.index("Control")


@pytest.mark.primitive(":plans")
async def test_plans_without_plans_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":plans<CR>")
        assert "Tron" not in ed.message
        assert ed.text == DECK
        assert not ed.modified


# --- ]v and [v ------------------------------------------------------------


@pytest.mark.primitive("]v")
async def test_next_plan_jumps_to_and_activates_the_first_plan(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press("]v")
        assert ed.row == TRON_ROW
        assert "vs Tron -2/+2" in status(ed)


@pytest.mark.primitive("]v")
async def test_next_plan_twice_reaches_the_second_plan(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press("]v ]v")
        assert ed.row == CONTROL_ROW
        assert "vs Control" in status(ed)


@pytest.mark.primitive("]v")
async def test_next_plan_after_the_last_stays_put(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press("]v ]v ]v")
        assert ed.row == CONTROL_ROW
        assert "vs Control" in status(ed)
        assert not ed.modified


@pytest.mark.primitive("]v")
async def test_next_plan_without_plans_stays_put(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} ]v")
        assert ed.row == GOBLIN_ROW
        assert "vs " not in status(ed)


@pytest.mark.primitive("[v")
async def test_previous_plan_jumps_back_and_activates_it(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{CONTROL_ROW + 1}G [v")
        assert ed.row == TRON_ROW
        assert "vs Tron" in status(ed)


@pytest.mark.primitive("[v")
async def test_previous_plan_before_the_first_stays_put(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{G_GOBLIN} [v")
        assert ed.row == GOBLIN_ROW
        assert "vs " not in status(ed)


# --- zo -------------------------------------------------------------------


@pytest.mark.primitive("zo")
async def test_zo_boards_every_copy_out_of_the_mainboard(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{TRON} {G_BOLT} zo")
        assert plan(ed.text, "Tron") == {"Lightning Bolt": -4, "Rest in Peace": 2}
        assert plan(ed.text, "Control") == {"Fire // Ice": -1}
        assert "vs Tron -4/+2" in status(ed)


@pytest.mark.primitive("zo")
async def test_zo_with_a_count_adds_a_new_out_line_to_the_active_plan(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{CONTROL} {G_GOBLIN} 2zo")
        assert plan(ed.text, "Control") == {"Fire // Ice": -1, "Goblin Guide": -2}
        assert plan(ed.text, "Tron") == TRON_BEFORE
        assert "    -2 Goblin Guide" in ed.lines[CONTROL_ROW:]


@pytest.mark.primitive("zo")
async def test_zo_is_clamped_to_the_copies_in_the_mainboard(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{CONTROL} {G_GOBLIN} 9zo")
        assert plan(ed.text, "Control")["Goblin Guide"] == -4


@pytest.mark.primitive("zo")
async def test_zo_leaves_the_deck_lists_alone(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{TRON} {G_BOLT} zo")
        head = PLAN_DECK[:PLAN_DECK.index("VS:")]
        assert ed.text.startswith(head)


@pytest.mark.primitive("zo")
async def test_zo_on_a_boarded_in_card_takes_it_back_out_of_the_plan(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{TRON} {G_RIP} zo")
        assert plan(ed.text, "Tron") == {"Lightning Bolt": -2}


@pytest.mark.primitive("zo")
async def test_zo_in_a_deck_with_one_plan_uses_it(tmp_path: Path) -> None:
    async with editor(tmp_path, ONE_PLAN_DECK) as ed:
        ed.press(f"{G_BOLT} zo")
        assert plan(ed.text, "Tron") == {"Lightning Bolt": -4, "Rest in Peace": 2}
        assert "vs Tron" in status(ed)


@pytest.mark.primitive("zo")
async def test_zo_with_several_plans_and_none_active_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{G_BOLT} zo")
        assert ed.is_error
        assert ed.text == PLAN_DECK


@pytest.mark.primitive("zo")
async def test_zo_without_any_plan_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_BOLT} zo")
        assert ed.is_error
        assert ed.text == DECK


@pytest.mark.primitive("zo")
@pytest.mark.parametrize("row", [3, 6, 11], ids=["blank", "zone-header", "section-header"])
async def test_zo_from_a_non_card_line_changes_nothing(tmp_path: Path, row: int) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{TRON} {row + 1}G zo")
        assert ed.text == PLAN_DECK
        assert ed.is_error


# --- zi -------------------------------------------------------------------


@pytest.mark.primitive("zi")
async def test_zi_boards_every_sideboard_copy_in(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{CONTROL} {G_RIP} zi")
        assert plan(ed.text, "Control") == {"Fire // Ice": -1, "Rest in Peace": 2}
        assert "vs Control -1/+2" in status(ed)


@pytest.mark.primitive("zi")
async def test_zi_with_a_count_boards_that_many_in(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{CONTROL} {G_RIP} 1zi")
        assert plan(ed.text, "Control") == {"Fire // Ice": -1, "Rest in Peace": 1}


@pytest.mark.primitive("zi")
async def test_zi_is_clamped_to_the_copies_in_the_sideboard(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{TRON} {G_RIP} zi")
        assert plan(ed.text, "Tron") == TRON_BEFORE
        assert ed.text == PLAN_DECK


@pytest.mark.primitive("zi")
async def test_zi_on_a_boarded_out_card_removes_its_entry_at_zero(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{TRON} {G_BOLT} zi")
        assert plan(ed.text, "Tron") == {"Rest in Peace": 2}
        assert not any("Lightning Bolt" in line for line in ed.lines[TRON_ROW:CONTROL_ROW])


@pytest.mark.primitive("zi")
async def test_zi_writes_into_the_active_plan_only(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(f"{CONTROL} {FIRE_ICE_ROW + 1}G zi")
        assert plan(ed.text, "Control") == {}
        assert plan(ed.text, "Tron") == TRON_BEFORE


@pytest.mark.primitive("zi")
async def test_zi_without_any_plan_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_RIP} zi")
        assert ed.is_error
        assert ed.text == DECK


UNDO_CASES = [
    f"{TRON} {G_BOLT} zo",
    f"{CONTROL} {G_GOBLIN} 2zo",
    f"{CONTROL} {G_RIP} zi",
    f"{TRON} {G_BOLT} zi",
]


@pytest.mark.primitive("zo", "zi")
@pytest.mark.parametrize("keys", UNDO_CASES, ids=["zo", "2zo-new", "zi-new", "zi-to-zero"])
async def test_one_undo_restores_the_text_before_boarding(tmp_path: Path, keys: str) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press(keys)
        assert ed.text != PLAN_DECK
        ed.press("u")
        assert ed.text == PLAN_DECK
        assert not ed.modified

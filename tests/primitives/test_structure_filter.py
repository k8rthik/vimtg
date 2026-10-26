"""The view filter: :filter and Space f.

Spec: docs/commands.md "Categories & layout" (filter grammar),
docs/keybindings.md "The leader (Space)", README "Categories".

CAT_DECK's six card lines: Lava Spike and Lightning Bolt are @burn, Goblin
Guide and Eidolon are @threats, Mountain and the sideboard's Rest in Peace
have no category.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import editor
from tests.primitives.test_structure_support import (
    CAT_DECK,
    dimmed_cards,
    dimmed_rows,
    rendered_rows,
)

pytestmark = pytest.mark.asyncio

CARDS = ("Lava Spike", "Lightning Bolt", "Goblin Guide", "Eidolon", "Mountain", "Rest in Peace")
BURN = {"Lava Spike", "Lightning Bolt"}
THREATS = {"Goblin Guide", "Eidolon"}
NONE = {"Mountain", "Rest in Peace"}
ALL = BURN | THREATS | NONE

GRAMMAR = [
    ("burn", ALL - BURN, "2/6"),
    ("-burn", BURN, "4/6"),
    ("burn|threats", NONE, "4/6"),
    ("burn+threats", ALL, "0/6"),
    ("burn<Space>-threats", ALL - BURN, "2/6"),
    ("-burn<Space>-threats", BURN | THREATS, "2/6"),
]
GRAMMAR_IDS = ["a", "-a", "a|b", "a+b", "a -b", "-a -b"]


@pytest.mark.primitive(":filter")
@pytest.mark.parametrize(("expr", "dimmed", "count"), GRAMMAR, ids=GRAMMAR_IDS)
async def test_filter_dims_every_card_failing_the_expression(
    tmp_path: Path, expr: str, dimmed: set[str], count: str
) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f":filter<Space>{expr}<CR>")
        assert dimmed_cards(ed, CARDS) == dimmed
        assert count in ed.message
        assert not ed.is_error


@pytest.mark.primitive("space f")
@pytest.mark.parametrize(("expr", "dimmed", "count"), GRAMMAR, ids=GRAMMAR_IDS)
async def test_space_f_prompt_takes_the_same_grammar(
    tmp_path: Path, expr: str, dimmed: set[str], count: str
) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"<Space>f {expr}<CR>")
        assert dimmed_cards(ed, CARDS) == dimmed
        assert count in ed.message


@pytest.mark.primitive(":filter")
@pytest.mark.xfail(
    strict=True,
    reason="BUG: '-' binds to one name in the documented grammar, so -burn|threats "
    "is (NOT burn) OR threats and dims only the burn cards; it dims burn and threats",
)
async def test_filter_negation_binds_tighter_than_or(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":filter<Space>-burn|threats<CR>")
        assert dimmed_cards(ed, CARDS) == BURN


@pytest.mark.primitive(":filter")
async def test_filter_never_dims_headers(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":filter<Space>burn<CR>")
        rows = dimmed_rows(ed)
        assert not [r for r in rows if "//" in r or "DCK:" in r or "SB:" in r]


@pytest.mark.primitive(":filter")
async def test_filter_leaves_the_deck_text_unmodified(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":filter<Space>burn<CR>")
        assert ed.text == CAT_DECK
        assert not ed.modified


@pytest.mark.primitive(":filter")
async def test_filter_suppresses_the_expansion_of_a_dimmed_cursor_card(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press("12G")  # Goblin Guide, whose details expand under it
        expanded = len(rendered_rows(ed))
        ed.press(":filter<Space>burn<CR>")
        assert ed.row == 11
        assert len(rendered_rows(ed)) < expanded
        assert len(rendered_rows(ed)) == len(ed.lines) + 1  # one row per line


@pytest.mark.primitive(":filter")
@pytest.mark.parametrize("clear", [":filter<CR>", ":filter!<CR>"])
async def test_bare_or_bang_filter_clears(tmp_path: Path, clear: str) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":filter<Space>burn<CR>")
        assert dimmed_cards(ed, CARDS)
        ed.press(clear)
        assert dimmed_cards(ed, CARDS) == set()
        assert not ed.is_error


@pytest.mark.primitive(":filter")
async def test_a_new_filter_replaces_the_old_one(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":filter<Space>burn<CR> :filter<Space>threats<CR>")
        assert dimmed_cards(ed, CARDS) == ALL - THREATS


@pytest.mark.primitive(":filter")
async def test_filter_tab_completes_a_category_after_the_last_bar(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":filter<Space>threats|bu<Tab><CR>")
        assert dimmed_cards(ed, CARDS) == NONE


@pytest.mark.primitive(":filter")
async def test_filter_tab_completes_a_category_after_a_minus(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":filter<Space>-thr<Tab><CR>")
        assert dimmed_cards(ed, CARDS) == THREATS


@pytest.mark.primitive(":filter")
async def test_filter_follows_category_edits(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":filter<Space>burn<CR> 16G :cat<Space>burn<CR>")
        assert "Mountain" not in dimmed_cards(ed, CARDS)


@pytest.mark.primitive("space f")
async def test_space_f_with_an_empty_prompt_clears_the_filter(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":filter<Space>burn<CR> <Space>f <CR>")
        assert dimmed_cards(ed, CARDS) == set()


@pytest.mark.primitive("space f")
async def test_space_f_escape_keeps_the_current_filter(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":filter<Space>burn<CR> <Space>f threats<Esc>")
        assert dimmed_cards(ed, CARDS) == ALL - BURN


@pytest.mark.primitive("space f")
async def test_space_f_leaves_the_deck_text_unmodified(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press("<Space>f burn<CR>")
        assert ed.text == CAT_DECK
        assert not ed.modified

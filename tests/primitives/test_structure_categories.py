"""Categories and layout: gc gC gl :category :categories :layout.

Spec: docs/deck-format.md "Categories", docs/commands.md "Categories &
layout", docs/keybindings.md "Categories (g prefix)", README "Categories"
and "Sections, layouts, and placement".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.primitives.harness import DECK, editor
from tests.primitives.structure_support import (
    CAT_DECK,
    GOBLIN_ROW,
    PLAN_DECK,
    PREFIX_DECK,
    card_signature,
    entries_in,
    entry,
    header_above,
)
from vimtg.domain.deck import DeckEntry
from vimtg.tui.widgets.command_line import CommandLine

pytestmark = pytest.mark.asyncio

G_GOBLIN = f"{GOBLIN_ROW + 1}G"
# CAT_DECK rows (1-based for G)
G_LAVA, G_BOLT, G_CAT_GOBLIN, G_MOUNTAIN = "8G", "9G", "12G", "16G"

# A type-layout deck whose Lightning Bolt carries a category, a tag and a
# comment (row 12).
TOKENS_DECK = DECK.replace(
    "    4 Lightning Bolt\n", "    4 Lightning Bolt  @burn  #core  // best\n"
)
# A deck whose own category starts like two presets (recursion, removal).
REACH_DECK = DECK.replace(
    "    4 Lightning Bolt\n", "    4 Lightning Bolt  @reach\n"
)


def _with(text: str, old: str, new: str) -> str:
    assert old in text
    return text.replace(old, new, 1)


def _main(text: str) -> list[DeckEntry]:
    return entries_in(text, "main")


# --- gc -------------------------------------------------------------------


@pytest.mark.primitive("gc")
async def test_gc_sets_the_category_token_two_spaces_after_the_name(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} gc burn<CR>")
        assert ed.text == _with(DECK, "    4 Goblin Guide\n", "    4 Goblin Guide  @burn\n")
        assert ed.modified


@pytest.mark.primitive("gc")
async def test_gc_replaces_the_cards_one_category(tmp_path: Path) -> None:
    async with editor(tmp_path, TOKENS_DECK) as ed:
        ed.press("13G gc removal<CR>")
        e = entry(ed.text, "Lightning Bolt")
        assert (e.category, e.tags, e.comment) == ("removal", frozenset({"core"}), "best")


@pytest.mark.primitive("gc")
async def test_gc_in_a_category_deck_moves_the_card_under_its_header(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"{G_BOLT} gc threats<CR>")
        assert entry(ed.text, "Lightning Bolt").category == "threats"
        assert header_above(ed.lines, "Lightning Bolt") == "// @threats"


@pytest.mark.primitive("gc")
async def test_gc_in_a_category_deck_creates_the_missing_header(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"{G_BOLT} gc reach<CR>")
        assert header_above(ed.lines, "Lightning Bolt") == "// @reach"
        assert header_above(ed.lines, "Lava Spike") == "// @burn"


@pytest.mark.primitive("gc")
async def test_gc_applies_to_every_card_of_a_visual_range(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} V jj gc burn<CR>")
        cats = {e.card_name: e.category for e in _main(ed.text)}
        assert cats == {
            "Goblin Guide": "burn", "Eidolon of the Great Revel": "burn",
            "Bonecrusher Giant // Stomp": "burn", "Lightning Bolt": "",
            "Fire // Ice": "", "Sacred Foundry": "", "Mountain": "",
        }


@pytest.mark.primitive("gc")
async def test_gc_tab_completes_from_the_decks_own_categories_first(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, REACH_DECK) as ed:
        ed.press(f"{G_GOBLIN} gc re")
        assert ed.screen.query_one("#command-line", CommandLine).ghost == "reach"
        ed.press("<Tab><CR>")
        assert entry(ed.text, "Goblin Guide").category == "reach"


@pytest.mark.primitive("gc")
async def test_gc_escape_cancels_without_a_change(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} gc burn<Esc>")
        assert ed.text == DECK
        assert not ed.modified


@pytest.mark.primitive("gc")
async def test_gc_on_a_header_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("7G gc burn<CR>")
        assert ed.text == DECK
        assert not ed.modified


@pytest.mark.primitive("gc")
async def test_gc_with_an_invalid_name_leaves_the_text_unchanged(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} gc x!y<CR>")
        assert ed.text == DECK
        assert "x!y" in ed.message


@pytest.mark.primitive("gc")
@pytest.mark.xfail(
    strict=True,
    reason="BUG: gc with an invalid name shows 'E: Invalid category' but not as an "
    "error (is_error False); :category x! flags the same message as an error",
)
async def test_gc_with_an_invalid_name_reports_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} gc x!y<CR>")
        assert ed.is_error


@pytest.mark.primitive("gc")
async def test_one_undo_restores_the_text_before_gc(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"{G_BOLT} gc threats<CR> u")
        assert ed.text == CAT_DECK
        assert not ed.modified


# --- gC -------------------------------------------------------------------


@pytest.mark.primitive("gC")
async def test_capital_gc_clears_the_category_and_keeps_tags_and_comment(tmp_path: Path) -> None:
    async with editor(tmp_path, TOKENS_DECK) as ed:
        ed.press("13G gC")
        e = entry(ed.text, "Lightning Bolt")
        assert (e.category, e.tags, e.comment) == ("", frozenset({"core"}), "best")
        assert ed.lines[12].strip() == "4 Lightning Bolt  #core  // best"


@pytest.mark.primitive("gC")
async def test_capital_gc_in_a_category_deck_moves_the_card_to_uncategorized(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"{G_BOLT} gC")
        assert entry(ed.text, "Lightning Bolt").category == ""
        assert header_above(ed.lines, "Lightning Bolt") == "// Uncategorized"


@pytest.mark.primitive("gC")
async def test_capital_gc_clears_every_card_of_a_visual_range(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"{G_CAT_GOBLIN} V j gC")
        cats = {e.card_name: e.category for e in _main(ed.text)}
        assert cats == {
            "Lava Spike": "burn", "Lightning Bolt": "burn", "Goblin Guide": "",
            "Eidolon of the Great Revel": "", "Mountain": "",
        }


@pytest.mark.primitive("gC")
async def test_capital_gc_on_an_uncategorized_card_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"{G_MOUNTAIN} gC")
        assert ed.text == CAT_DECK
        assert not ed.modified


@pytest.mark.primitive("gC")
async def test_one_undo_restores_the_text_before_capital_gc(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"{G_BOLT} gC u")
        assert ed.text == CAT_DECK
        assert not ed.modified


# --- gl and :layout -------------------------------------------------------


@pytest.mark.primitive("gl")
async def test_gl_regroups_a_type_deck_by_category_uncategorized_last(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, TOKENS_DECK) as ed:
        ed.press("gl")
        assert header_above(ed.lines, "Lightning Bolt") == "// @burn"
        for card in ("Goblin Guide", "Mountain", "Fire // Ice"):
            assert header_above(ed.lines, card) == "// Uncategorized"
        burn = ed.lines.index("    // @burn")
        assert burn < ed.lines.index("    // Uncategorized")
        assert card_signature(ed.text) == card_signature(TOKENS_DECK)


@pytest.mark.primitive("gl")
async def test_gl_regroups_a_category_deck_by_type_keeping_every_token(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press("gl")
        assert header_above(ed.lines, "Goblin Guide") == "// Creatures"
        assert header_above(ed.lines, "Lightning Bolt") == "// Instants"
        assert header_above(ed.lines, "Lava Spike") == "// Sorceries"
        assert header_above(ed.lines, "Mountain") == "// Lands"
        assert card_signature(ed.text) == card_signature(CAT_DECK)


@pytest.mark.primitive("gl", ":layout")
async def test_gl_twice_round_trips_a_canonical_type_layout(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":layout<Space>type<CR>")
        typed = ed.text
        ed.press("gl gl")
        assert ed.text == typed


@pytest.mark.primitive("gl")
@pytest.mark.xfail(
    strict=True,
    reason="BUG: gl gl on a canonical category deck reorders the groups "
    "(@burn, @threats -> @threats, @burn); toggling should be lossless",
)
async def test_gl_twice_round_trips_a_canonical_category_layout(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press("gl gl")
        assert ed.text == CAT_DECK


@pytest.mark.primitive("gl")
async def test_gl_twice_loses_no_card_zone_count_or_category(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press("gl gl")
        assert card_signature(ed.text) == card_signature(CAT_DECK)


@pytest.mark.primitive("gl")
async def test_gl_carries_plans_and_the_sideboard_over_verbatim(tmp_path: Path) -> None:
    async with editor(tmp_path, PLAN_DECK) as ed:
        ed.press("gl")
        tail = PLAN_DECK[PLAN_DECK.index("SB:\n"):]
        assert ed.text.endswith(tail)


@pytest.mark.primitive("gl")
async def test_gl_keeps_prefix_style_zones_prefixed(tmp_path: Path) -> None:
    async with editor(tmp_path, PREFIX_DECK) as ed:
        ed.press("gl")
        assert "SB: 2 Rest in Peace" in ed.lines
        assert "MB: 1 Lava Spike" in ed.lines
        assert "SB:" not in ed.lines and "MB:" not in ed.lines


@pytest.mark.primitive("gl")
async def test_gl_to_type_layout_without_card_data_is_refused(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK, cards=False) as ed:
        ed.press("gl")
        assert ed.text == CAT_DECK
        assert ed.is_error


@pytest.mark.primitive("gl")
async def test_one_undo_restores_the_text_before_gl(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("gl")
        assert ed.text != DECK
        ed.press("u")
        assert ed.text == DECK
        assert not ed.modified


@pytest.mark.primitive(":layout")
async def test_layout_type_groups_by_card_type(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":layout<Space>type<CR>")
        assert header_above(ed.lines, "Eidolon of the Great Revel") == "// Creatures"
        assert header_above(ed.lines, "Lava Spike") == "// Sorceries"
        assert "    // @burn" not in ed.lines


@pytest.mark.primitive(":layout")
async def test_layout_category_groups_by_category(tmp_path: Path) -> None:
    async with editor(tmp_path, TOKENS_DECK) as ed:
        ed.press(":layout<Space>category<CR>")
        assert header_above(ed.lines, "Lightning Bolt") == "// @burn"
        assert header_above(ed.lines, "Goblin Guide") == "// Uncategorized"
        assert "    // Creature" not in ed.lines


@pytest.mark.primitive(":layout")
async def test_layout_category_on_a_category_layout_changes_nothing(
    tmp_path: Path,
) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":layout<Space>category<CR>")
        assert ed.text == CAT_DECK


@pytest.mark.primitive(":layout")
@pytest.mark.parametrize("text", [DECK, CAT_DECK], ids=["from-type", "from-category"])
async def test_bare_layout_toggles_like_gl(tmp_path: Path, text: str) -> None:
    async with editor(tmp_path, text) as ed:
        ed.press("gl")
        by_key = ed.text
    async with editor(tmp_path, text, name="again.deck") as ed:
        ed.press(":layout<CR>")
        assert ed.text == by_key != text


@pytest.mark.primitive(":layout")
async def test_layout_with_an_unknown_mode_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":layout<Space>colour<CR>")
        assert ed.text == DECK
        assert ed.is_error


@pytest.mark.primitive(":layout")
async def test_layout_type_without_card_data_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK, cards=False) as ed:
        ed.press(":layout<Space>type<CR>")
        assert ed.text == CAT_DECK
        assert ed.is_error


@pytest.mark.primitive(":layout")
@pytest.mark.parametrize("mode", ["type", "category"])
async def test_one_undo_restores_the_text_before_layout(tmp_path: Path, mode: str) -> None:
    text = CAT_DECK if mode == "type" else DECK
    async with editor(tmp_path, text) as ed:
        ed.press(f":layout<Space>{mode}<CR>")
        assert ed.text != text
        ed.press("u")
        assert ed.text == text


# --- :category ------------------------------------------------------------


@pytest.mark.primitive(":category")
async def test_category_sets_the_cursor_cards_category(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} :category<Space>burn<CR>")
        assert ed.text == _with(DECK, "    4 Goblin Guide\n", "    4 Goblin Guide  @burn\n")


@pytest.mark.primitive(":category")
async def test_cat_is_an_alias_of_category(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} :cat<Space>burn<CR>")
        assert entry(ed.text, "Goblin Guide").category == "burn"


@pytest.mark.primitive(":category")
async def test_category_with_a_range_sets_every_card_in_it(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":8,13category<Space>burn<CR>")
        cats = {e.card_name: e.category for e in _main(ed.text)}
        assert cats == {
            "Goblin Guide": "burn", "Eidolon of the Great Revel": "burn",
            "Bonecrusher Giant // Stomp": "burn", "Lightning Bolt": "burn",
            "Fire // Ice": "", "Sacred Foundry": "", "Mountain": "",
        }


@pytest.mark.primitive(":category")
async def test_category_in_a_category_deck_moves_the_card(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"{G_MOUNTAIN} :category<Space>lands<CR>")
        assert header_above(ed.lines, "Mountain") == "// @lands"


@pytest.mark.primitive(":category")
async def test_category_bang_clears_and_refiles_to_uncategorized(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"{G_CAT_GOBLIN} :category!<CR>")
        assert entry(ed.text, "Goblin Guide").category == ""
        assert header_above(ed.lines, "Goblin Guide") == "// Uncategorized"


@pytest.mark.primitive(":category")
async def test_category_bang_with_a_range_clears_every_card(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":%category!<CR>")
        assert all(e.category == "" for e in _main(ed.text))


@pytest.mark.primitive(":category")
async def test_category_with_an_invalid_name_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} :category<Space>x!<CR>")
        assert ed.text == DECK
        assert ed.is_error


@pytest.mark.primitive(":category")
async def test_category_name_longer_than_32_chars_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f"{G_GOBLIN} :category<Space>{'a' * 33}<CR>")
        assert ed.text == DECK
        assert ed.is_error


@pytest.mark.primitive(":category")
@pytest.mark.parametrize("cmd", [":category<Space>threats<CR>", ":category!<CR>"])
async def test_one_undo_restores_the_text_before_category(tmp_path: Path, cmd: str) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"{G_BOLT} {cmd}")
        assert ed.text != CAT_DECK
        ed.press("u")
        assert ed.text == CAT_DECK
        assert not ed.modified


# --- :categories ----------------------------------------------------------


@pytest.mark.primitive(":categories")
async def test_categories_lists_each_category_with_its_count(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":categories<CR>")
        assert re.search(r"@burn\W{0,3}2\b", ed.message)
        assert re.search(r"@threats\W{0,3}2\b", ed.message)
        assert ed.text == CAT_DECK


@pytest.mark.primitive(":categories")
async def test_categories_counts_follow_the_deck(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f"{G_MOUNTAIN} :cat<Space>burn<CR> :categories<CR>")
        assert re.search(r"@burn\W{0,3}3\b", ed.message)


@pytest.mark.primitive(":categories")
async def test_categories_name_lists_that_categorys_cards(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":categories<Space>burn<CR>")
        assert "Lava Spike" in ed.message and "Lightning Bolt" in ed.message
        assert "Goblin Guide" not in ed.message


@pytest.mark.primitive(":categories")
async def test_cats_is_an_alias_of_categories(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":cats<Space>threats<CR>")
        assert "Goblin Guide" in ed.message and "Lava Spike" not in ed.message
        assert not ed.modified


@pytest.mark.primitive(":categories")
async def test_categories_on_a_deck_without_categories_lists_none(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":categories<CR>")
        assert "@" not in ed.message
        assert ed.text == DECK


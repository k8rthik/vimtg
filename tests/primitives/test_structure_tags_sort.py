"""Deck tags and sorting: :dtag :duntag :sort.

Spec: docs/commands.md "Deck tags" and "Editing" (:sort), docs/deck-format.md
"Metadata keys", README "Bulk editing". Card facts come from
tests/fixtures/scryfall_sample.json.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.primitives.harness import DECK, editor
from tests.primitives.structure_support import CAT_DECK, card_signature, zone
from vimtg.data.deck_repository import parse_deck_text

pytestmark = pytest.mark.asyncio


def _tags(text: str) -> frozenset[str]:
    return parse_deck_text(text).metadata.tags


def _tags_line(lines: list[str]) -> str:
    found = [line for line in lines if line.startswith("// Tags:")]
    assert len(found) == 1, found
    return found[0]


# --- :dtag ----------------------------------------------------------------


@pytest.mark.primitive(":dtag")
async def test_dtag_fills_the_empty_tags_line(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":dtag<Space>aggro<CR>")
        assert ed.text == DECK.replace("// Tags:\n", "// Tags: aggro\n")
        assert ed.modified


@pytest.mark.primitive(":dtag")
async def test_dtag_adds_several_tags_at_once(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":dtag<Space>aggro<Space>burn<CR>")
        assert _tags(ed.text) == {"aggro", "burn"}


@pytest.mark.primitive(":dtag")
async def test_dtag_keeps_the_existing_tags(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":dtag<Space>burn<CR>")
        assert _tags(ed.text) == {"aggro", "burn"}
        assert _tags_line(ed.lines).count("aggro") == 1


@pytest.mark.primitive(":dtag")
async def test_dtag_of_a_tag_already_there_does_not_repeat_it(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":dtag<Space>aggro<CR>")
        assert _tags_line(ed.lines) == "// Tags: aggro"


@pytest.mark.primitive(":dtag")
async def test_dtag_creates_the_tags_line_a_saved_file_lacked(tmp_path: Path) -> None:
    text = "// Deck: Bare\n// Format: modern\n\nDCK:\n    4 Goblin Guide\n"
    async with editor(tmp_path, text) as ed:
        ed.press(":dtag<Space>aggro<CR> :w<CR>")
        saved = ed.saved()
    assert _tags(saved) == {"aggro"}
    assert saved.count("// Tags:") == 1


@pytest.mark.primitive(":dtag")
@pytest.mark.parametrize("args", ["", "<Space>a!b"], ids=["no-name", "invalid-name"])
async def test_dtag_without_a_valid_name_is_an_error(tmp_path: Path, args: str) -> None:
    async with editor(tmp_path) as ed:
        ed.press(f":dtag{args}<CR>")
        assert ed.is_error
        assert ed.text == DECK
        assert not ed.modified


@pytest.mark.primitive(":dtag")
async def test_one_undo_restores_the_text_before_dtag(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":dtag<Space>burn<CR> u")
        assert ed.text == CAT_DECK
        assert not ed.modified


# --- :duntag --------------------------------------------------------------


@pytest.mark.primitive(":duntag")
async def test_duntag_of_the_last_tag_keeps_the_empty_line(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":duntag<Space>aggro<CR>")
        assert ed.text == CAT_DECK.replace("// Tags: aggro\n", "// Tags:\n")


@pytest.mark.primitive(":duntag")
async def test_duntag_removes_only_the_named_tags(tmp_path: Path) -> None:
    text = DECK.replace("// Tags:\n", "// Tags: aggro, burn, prowess\n")
    async with editor(tmp_path, text) as ed:
        ed.press(":duntag<Space>burn<Space>prowess<CR>")
        assert _tags(ed.text) == {"aggro"}


@pytest.mark.primitive(":duntag")
async def test_duntag_of_a_missing_tag_changes_nothing(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":duntag<Space>control<CR>")
        assert ed.text == CAT_DECK
        assert not ed.modified
        assert "control" in ed.message


@pytest.mark.primitive(":duntag")
@pytest.mark.parametrize("args", ["", "<Space>a!b"], ids=["no-name", "invalid-name"])
async def test_duntag_without_a_valid_name_is_an_error(tmp_path: Path, args: str) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(f":duntag{args}<CR>")
        assert ed.is_error
        assert ed.text == CAT_DECK


@pytest.mark.primitive(":duntag")
async def test_one_undo_restores_the_text_before_duntag(tmp_path: Path) -> None:
    async with editor(tmp_path, CAT_DECK) as ed:
        ed.press(":duntag<Space>aggro<CR> u")
        assert ed.text == CAT_DECK
        assert not ed.modified


# --- :sort ----------------------------------------------------------------

# One unheaded mainboard section (rows 5-11) and a sideboard.
SORT_DECK = (
    "// Deck: Sort\n// Format: modern\n// Tags:\n\n"
    "DCK:\n"
    "    2 Lightning Bolt  @burn\n"
    "    1 Sacred Foundry\n"
    "    3 Rest in Peace  @hate\n"
    "    6 Bonecrusher Giant // Stomp\n"
    "    5 Fire // Ice\n"
    "    4 Goblin Guide  @threats\n"
    "    7 Mountain\n"
    "\n"
    "SB:\n"
    "    1 Eidolon of the Great Revel\n"
)
IN_SECTION = "6G"

# Facts from the sample card data, per card.
CMC = {
    "Lightning Bolt": 1, "Sacred Foundry": 0, "Rest in Peace": 2, "Goblin Guide": 1,
    "Fire // Ice": 4, "Bonecrusher Giant // Stomp": 3, "Mountain": 0,
}
QTY = {
    "Sacred Foundry": 1, "Lightning Bolt": 2, "Rest in Peace": 3, "Goblin Guide": 4,
    "Fire // Ice": 5, "Bonecrusher Giant // Stomp": 6, "Mountain": 7,
}
TYPE_RANK = {  # creatures, then instants, then lands, as the type layout orders them
    "Goblin Guide": 0, "Bonecrusher Giant // Stomp": 0, "Lightning Bolt": 1,
    "Fire // Ice": 1, "Sacred Foundry": 2, "Mountain": 2,
}
COLOR_RANK = {  # WUBRG, then multicolour
    "Rest in Peace": 0, "Lightning Bolt": 4, "Goblin Guide": 4,
    "Bonecrusher Giant // Stomp": 4, "Fire // Ice": 5,
}
RARITY_RANK = {  # common < uncommon < rare
    "Mountain": 0, "Lightning Bolt": 1, "Fire // Ice": 1, "Sacred Foundry": 2,
    "Rest in Peace": 2, "Goblin Guide": 2, "Bonecrusher Giant // Stomp": 2,
}
PRICE = {
    "Fire // Ice": 0.25, "Bonecrusher Giant // Stomp": 0.75, "Lightning Bolt": 1.50,
    "Goblin Guide": 3.50, "Rest in Peace": 4.00, "Sacred Foundry": 12.00,
}
POWER = {"Goblin Guide": 2, "Bonecrusher Giant // Stomp": 4}
TOUGHNESS = {"Goblin Guide": 2, "Bonecrusher Giant // Stomp": 3}


def _main_order(text: str) -> list[str]:
    return [e.card_name for e in parse_deck_text(text).mainboard()]


def _ranked(order: list[str], rank: dict[str, float]) -> list[float]:
    """The ranks of the ranked cards, in deck order."""
    return [rank[name] for name in order if name in rank]


@pytest.mark.primitive(":sort")
async def test_sort_name_orders_the_section_alphabetically(tmp_path: Path) -> None:
    async with editor(tmp_path, SORT_DECK) as ed:
        ed.press(f"{IN_SECTION} :sort<Space>name<CR>")
        assert _main_order(ed.text) == [
            "Bonecrusher Giant // Stomp", "Fire // Ice", "Goblin Guide",
            "Lightning Bolt", "Mountain", "Rest in Peace", "Sacred Foundry",
        ]
        assert card_signature(ed.text) == card_signature(SORT_DECK)


@pytest.mark.primitive(":sort")
async def test_sort_qty_orders_by_quantity(tmp_path: Path) -> None:
    async with editor(tmp_path, SORT_DECK) as ed:
        ed.press(f"{IN_SECTION} :sort<Space>qty<CR>")
        assert _main_order(ed.text) == sorted(QTY, key=QTY.__getitem__)


@pytest.mark.primitive(":sort")
async def test_sort_category_groups_by_name_uncategorized_last(tmp_path: Path) -> None:
    async with editor(tmp_path, SORT_DECK) as ed:
        ed.press(f"{IN_SECTION} :sort<Space>category<CR>")
        order = _main_order(ed.text)
        assert order[:3] == ["Lightning Bolt", "Rest in Peace", "Goblin Guide"]
        assert set(order[3:]) == {
            "Sacred Foundry", "Fire // Ice", "Bonecrusher Giant // Stomp", "Mountain",
        }


@pytest.mark.primitive(":sort")
@pytest.mark.parametrize(
    ("field", "rank"),
    [
        ("cmc", CMC), ("type", TYPE_RANK), ("color", COLOR_RANK),
        ("rarity", RARITY_RANK), ("price", PRICE), ("power", POWER),
        ("toughness", TOUGHNESS),
    ],
)
async def test_sort_by_a_card_field_orders_by_that_field(
    tmp_path: Path, field: str, rank: dict[str, float]
) -> None:
    async with editor(tmp_path, SORT_DECK) as ed:
        ed.press(f"{IN_SECTION} :sort<Space>{field}<CR>")
        ranks = _ranked(_main_order(ed.text), rank)
        assert ranks == sorted(ranks)
        assert ranks != _ranked(_main_order(SORT_DECK), rank)  # the sort did work
        assert not ed.is_error


@pytest.mark.primitive(":sort")
async def test_sort_without_a_field_sorts_by_mana_value(tmp_path: Path) -> None:
    async with editor(tmp_path, SORT_DECK) as ed:
        ed.press(f"{IN_SECTION} :sort<CR>")
        ranks = _ranked(_main_order(ed.text), CMC)
        assert ranks == sorted(ranks)


@pytest.mark.primitive(":sort")
async def test_sort_bang_reverses_the_order(tmp_path: Path) -> None:
    async with editor(tmp_path, SORT_DECK) as ed:
        ed.press(f"{IN_SECTION} :sort!<Space>qty<CR>")
        assert _main_order(ed.text) == sorted(QTY, key=QTY.__getitem__, reverse=True)


@pytest.mark.primitive(":sort")
async def test_sort_touches_only_the_cursors_section(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G :sort<Space>name<CR>")
        assert ed.lines[7:10] == [
            "    3 Bonecrusher Giant // Stomp",
            "    2 Eidolon of the Great Revel",
            "    4 Goblin Guide",
        ]
        deck_lines = DECK.split("\n")[:-1]
        assert ed.lines[:7] == deck_lines[:7]
        assert ed.lines[10:] == deck_lines[10:]


@pytest.mark.primitive(":sort")
async def test_sort_whole_deck_keeps_headers_and_zones_in_place(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press(":%sort<Space>name<CR>")
        order = _main_order(ed.text)
        assert order == sorted(order, key=str.lower)
        deck_lines = DECK.split("\n")
        for row in (4, 6, 11, 15, 19):
            assert ed.lines[row] == deck_lines[row]
        assert zone(ed.text, "side") == {"Rest in Peace": 2}
        assert card_signature(ed.text) == card_signature(DECK)


@pytest.mark.primitive(":sort")
async def test_sort_with_a_line_range_sorts_only_those_lines(tmp_path: Path) -> None:
    async with editor(tmp_path, SORT_DECK) as ed:
        ed.press(":6,8sort<Space>name<CR>")
        assert _main_order(ed.text) == [
            "Lightning Bolt", "Rest in Peace", "Sacred Foundry",
            "Bonecrusher Giant // Stomp", "Fire // Ice", "Goblin Guide", "Mountain",
        ]


@pytest.mark.primitive(":sort")
async def test_sort_of_a_sorted_section_is_not_a_change(tmp_path: Path) -> None:
    async with editor(tmp_path) as ed:
        ed.press("8G :sort<Space>qty<CR>")
        ed.press(":sort<Space>qty<CR>")
        ed.press("u")
        assert ed.text == DECK


@pytest.mark.primitive(":sort")
async def test_sort_with_an_unknown_field_is_an_error(tmp_path: Path) -> None:
    async with editor(tmp_path, SORT_DECK) as ed:
        ed.press(f"{IN_SECTION} :sort<Space>colour<CR>")
        assert ed.is_error
        assert ed.text == SORT_DECK
        assert not ed.modified


@pytest.mark.primitive(":sort")
@pytest.mark.parametrize("cmd", [":sort<Space>name<CR>", ":sort!<CR>", ":%sort<Space>price<CR>"])
async def test_one_undo_restores_the_text_before_sort(tmp_path: Path, cmd: str) -> None:
    async with editor(tmp_path, SORT_DECK) as ed:
        ed.press(f"{IN_SECTION} {cmd}")
        assert ed.text != SORT_DECK
        ed.press("u")
        assert ed.text == SORT_DECK
        assert not ed.modified

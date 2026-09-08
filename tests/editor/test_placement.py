"""Tests for mainboard placement — the single policy behind search
inserts, EDHREC inserts, and md zone moves."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.placement import (
    PlacementPolicy,
    place_mainboard_card,
    reconcile_category_sections,
)
from vimtg.editor.sections import normalize_sections


def _buf(*lines: str) -> Buffer:
    return Buffer.from_text("\n".join(lines) + "\n")


def _lines(buf: Buffer) -> list[str]:
    return buf.to_text().splitlines()


def _insert(buf: Buffer, policy: PlacementPolicy, text: str, **kw: object) -> Buffer:
    placed = place_mainboard_card(buf, policy, **kw)  # type: ignore[arg-type]
    out = placed.buffer.insert_line(placed.row, f"{placed.indent}{text}")
    if placed.category:
        out = out.set_category(placed.row, placed.category)
    return out


SORT = PlacementPolicy(auto_sort=True, type_line="Sorcery")
FREE = PlacementPolicy(auto_sort=False, type_line="Sorcery")


class TestTypeLayout:
    def test_joins_type_section_in_any_spelling(self) -> None:
        buf = _buf("// Sorcery", "4 Ponder", "", "// Lands", "20 Island")
        out = _lines(_insert(buf, SORT, "2 Preordain"))
        assert out[:3] == ["// Sorcery", "4 Ponder", "2 Preordain"]

    def test_creates_canonical_header(self) -> None:
        buf = _buf("// Lands", "20 Island")
        out = _lines(_insert(buf, SORT, "2 Preordain"))
        assert out[-2:] == ["// Sorceries", "2 Preordain"]

    def test_unknown_type_goes_to_other(self) -> None:
        buf = _buf("// Lands", "20 Island")
        out = _lines(_insert(buf, PlacementPolicy(True, "Conspiracy"), "1 Weird"))
        assert out[-2:] == ["// Other", "1 Weird"]

    def test_unresolved_card_goes_to_other(self) -> None:
        buf = _buf("// Lands", "20 Island")
        out = _lines(_insert(buf, PlacementPolicy(True, None), "1 Typo"))
        assert out[-2:] == ["// Other", "1 Typo"]

    def test_open_row_is_ignored(self) -> None:
        buf = _buf("// Sorcery", "4 Ponder", "", "// Lands", "20 Island")
        out = _lines(_insert(buf, SORT, "2 Preordain", open_row=5))
        assert out.index("2 Preordain") == 2

    def test_inside_dck_block_is_indented(self) -> None:
        buf = _buf("DCK:", "", "    // Lands", "    20 Island")
        placed = place_mainboard_card(buf, SORT)
        out = _lines(placed.buffer.insert_line(placed.row, f"{placed.indent}2 Preordain"))
        assert out[-2:] == ["    // Sorceries", "    2 Preordain"]
        assert placed.lines_added == 2
        with_card = placed.buffer.insert_line(placed.row, "    2 Preordain")
        assert normalize_sections(with_card) is with_card


class TestCategoryLayout:
    def test_opened_under_category_header_inherits_it(self) -> None:
        buf = _buf("// @ramp", "1 Cultivate", "", "// @draw", "1 Opt")
        placed = place_mainboard_card(buf, SORT, open_row=2)
        assert placed.row == 2
        assert placed.category == "ramp"

    def test_opened_under_uncategorized_inherits_nothing(self) -> None:
        buf = _buf("// @ramp", "1 Cultivate", "", "// Uncategorized", "1 Opt")
        placed = place_mainboard_card(buf, SORT, open_row=5)
        assert placed.row == 5
        assert placed.category == ""

    def test_card_with_token_joins_its_category_section(self) -> None:
        buf = _buf("// @ramp", "1 Cultivate", "", "// @draw", "1 Opt")
        out = _lines(_insert(buf, SORT, "1 Farseek  @ramp", category="ramp"))
        assert out[:3] == ["// @ramp", "1 Cultivate", "1 Farseek  @ramp"]

    def test_card_with_new_token_gets_a_section(self) -> None:
        buf = _buf("// @ramp", "1 Cultivate")
        out = _lines(_insert(buf, SORT, "1 Shock  @removal", category="removal"))
        assert out[-2:] == ["// @removal", "1 Shock  @removal"]

    def test_no_position_no_token_goes_to_uncategorized(self) -> None:
        buf = _buf("// @ramp", "1 Cultivate")
        out = _lines(_insert(buf, SORT, "1 Opt"))
        assert out[-2:] == ["// Uncategorized", "1 Opt"]

    def test_type_line_is_irrelevant_in_category_layout(self) -> None:
        # The bug the EDHREC path had: creating '// Sorceries' in a
        # category-grouped deck
        buf = _buf("// @ramp", "1 Cultivate")
        out = _lines(_insert(buf, SORT, "1 Ponder"))
        assert "// Sorceries" not in out


class TestFreePlacement:
    def test_stays_where_opened(self) -> None:
        buf = _buf("// Lands", "20 Island", "", "// Sorcery", "4 Ponder")
        placed = place_mainboard_card(buf, FREE, open_row=2)
        assert placed.row == 2
        assert placed.category == ""

    def test_no_position_appends_to_mainboard(self) -> None:
        buf = _buf("// Sorcery", "4 Ponder", "", "SB: 1 Duress")
        placed = place_mainboard_card(buf, FREE)
        assert placed.row == 2

    def test_inherits_category_of_where_it_lands(self) -> None:
        buf = _buf("// @ramp", "1 Cultivate", "", "// @draw", "1 Opt")
        placed = place_mainboard_card(buf, FREE, open_row=5)
        assert placed.category == "draw"

    def test_matches_block_indent(self) -> None:
        buf = _buf("DCK:", "", "    // Lands", "    20 Island")
        placed = place_mainboard_card(buf, FREE, open_row=4)
        assert placed.indent == "    "


class TestReconcileCategorySections:
    def test_type_layout_is_untouched(self) -> None:
        buf = _buf("// Sorceries", "4 Ponder  @draw")
        assert reconcile_category_sections(buf) is buf

    def test_matching_deck_is_untouched(self) -> None:
        buf = _buf("// @ramp", "1 Cultivate  @ramp", "", "// Uncategorized", "1 Opt")
        assert reconcile_category_sections(buf) is buf

    def test_retagged_card_moves_to_its_section(self) -> None:
        buf = _buf(
            "// @ramp", "1 Cultivate  @ramp", "1 Opt  @draw", "",
            "// @draw", "1 Ponder  @draw",
        )
        out = _lines(reconcile_category_sections(buf))
        assert out == [
            "// @ramp", "1 Cultivate  @ramp", "",
            "// @draw", "1 Ponder  @draw", "1 Opt  @draw",
        ]

    def test_new_category_gets_a_section(self) -> None:
        buf = _buf("// @ramp", "1 Cultivate  @ramp", "1 Shock  @removal")
        out = _lines(reconcile_category_sections(buf))
        assert out == ["// @ramp", "1 Cultivate  @ramp", "", "// @removal", "1 Shock  @removal"]

    def test_cleared_card_moves_to_uncategorized(self) -> None:
        buf = _buf(
            "// @ramp", "1 Cultivate  @ramp", "1 Opt", "",
            "// Uncategorized", "1 Brainstorm",
        )
        out = _lines(reconcile_category_sections(buf))
        assert out == [
            "// @ramp", "1 Cultivate  @ramp", "",
            "// Uncategorized", "1 Brainstorm", "1 Opt",
        ]

    def test_tagged_card_leaves_uncategorized(self) -> None:
        buf = _buf("// @ramp", "1 Cultivate  @ramp", "", "// Uncategorized", "1 Opt  @ramp")
        out = _lines(reconcile_category_sections(buf))
        assert out[:3] == ["// @ramp", "1 Cultivate  @ramp", "1 Opt  @ramp"]
        assert "1 Opt  @ramp" not in out[3:]

    def test_inside_dck_block_keeps_indent(self) -> None:
        buf = _buf("DCK:", "", "    // @ramp", "    1 Cultivate  @ramp", "    1 Opt  @draw")
        out = _lines(reconcile_category_sections(buf))
        assert out[-2:] == ["    // @draw", "    1 Opt  @draw"]

    def test_cards_under_type_headers_are_left_alone(self) -> None:
        # A mixed deck: category layout detected, but a stray type header
        # makes no claim about its cards' categories
        buf = _buf("// @ramp", "1 Cultivate  @ramp", "", "// Lands", "20 Forest")
        assert reconcile_category_sections(buf) is buf

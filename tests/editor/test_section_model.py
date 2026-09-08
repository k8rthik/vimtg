"""Tests for the parsed section model — the one definition of a
section's identity and extent that insert, counts, cleanup, and
category lookup all share."""

from __future__ import annotations

from vimtg.domain.section_keys import SectionKey, SectionKind
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.section_model import (
    find_section,
    parse_sections,
    section_at,
)


def _buf(*lines: str) -> Buffer:
    return Buffer.from_text("\n".join(lines) + "\n")


class TestExtent:
    def test_section_runs_to_next_header(self) -> None:
        buf = _buf("// Creatures", "4 Elves", "", "// note", "2 Goyf", "", "// Lands", "20 Forest")
        creatures, lands = parse_sections(buf)
        assert creatures.header_row == 0
        assert creatures.end == 6
        assert creatures.card_rows == (1, 4)
        assert lands.header_row == 6
        assert lands.end == 8

    def test_plan_header_ends_a_section(self) -> None:
        buf = _buf("// Lands", "20 Forest", "", "VS: Tron", "    -4 Forest")
        (lands,) = parse_sections(buf)
        assert lands.end == 3
        assert lands.card_rows == (1,)

    def test_foreign_zone_lines_are_not_section_cards(self) -> None:
        buf = _buf("// Creatures", "", "SB: 1 Duress", "4 Elves")
        (creatures,) = parse_sections(buf)
        assert creatures.zone is LineType.CARD_ENTRY
        assert creatures.card_rows == (3,)

    def test_insert_row_follows_last_card_of_the_zone(self) -> None:
        buf = _buf("// Creatures", "4 Elves", "SB: 1 Duress", "4 Bolt", "", "// Lands")
        creatures = parse_sections(buf)[0]
        assert creatures.insert_row == 4

    def test_insert_row_of_empty_section_is_under_header(self) -> None:
        buf = _buf("// Creatures", "", "// Lands", "20 Forest")
        creatures = parse_sections(buf)[0]
        assert creatures.is_empty
        assert creatures.insert_row == 1

    def test_comment_under_header_does_not_move_insert_row(self) -> None:
        buf = _buf("// Creatures", "// keep these", "4 Elves")
        assert parse_sections(buf)[0].insert_row == 3


class TestZones:
    def test_zone_label_header_groups_its_zone(self) -> None:
        buf = _buf("// Sideboard", "SB: 2 Duress", "1 Bolt")
        (side,) = parse_sections(buf)
        assert side.zone is LineType.SIDEBOARD_ENTRY
        assert side.card_rows == (1,)

    def test_indented_type_header_takes_the_enclosing_block_zone(self) -> None:
        buf = _buf("SB:", "    // Creatures", "    2 Elves")
        block, creatures = parse_sections(buf)
        assert block.key == SectionKey(SectionKind.ZONE_BLOCK, "SB")
        assert block.is_structural
        assert creatures.zone is LineType.SIDEBOARD_ENTRY
        assert creatures.card_rows == (2,)
        assert creatures.indent == "    "

    def test_dck_block_type_header_is_mainboard(self) -> None:
        buf = _buf("DCK:", "    // Creatures", "    4 Elves")
        creatures = parse_sections(buf)[1]
        assert creatures.zone is LineType.CARD_ENTRY
        assert creatures.card_rows == (2,)


class TestLookup:
    def test_find_by_key_ignores_spelling(self) -> None:
        buf = _buf("// Sorcery", "4 Ponder")
        found = find_section(parse_sections(buf), SectionKey(SectionKind.TYPE, "Sorcery"))
        assert found is not None and found.header_row == 0

    def test_find_missing_is_none(self) -> None:
        buf = _buf("// Sorcery", "4 Ponder")
        assert find_section(parse_sections(buf), SectionKey(SectionKind.TYPE, "Land")) is None

    def test_section_at_covers_header_and_body(self) -> None:
        buf = _buf("1 Opt", "// @ramp", "4 Cultivate", "", "// @draw", "2 Opt")
        sections = parse_sections(buf)
        assert section_at(sections, 0) is None
        assert section_at(sections, 1) is sections[0]
        assert section_at(sections, 3) is sections[0]
        assert section_at(sections, 5) is sections[1]

    def test_no_headers_no_sections(self) -> None:
        assert parse_sections(_buf("4 Elves", "1 Bolt")) == ()

"""DCK: — Python-style block header for the main deck."""

from __future__ import annotations

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.deck import DeckSection
from vimtg.domain.deck_lines import is_deck_header
from vimtg.editor.buffer import Buffer, LineType, classify_line
from vimtg.editor.cursor import Cursor
from vimtg.editor.operators import move_to_zone
from vimtg.editor.sections import normalize_sections


class TestClassification:
    def test_dck_line_is_a_section_header(self):
        assert classify_line("DCK:") is LineType.SECTION_HEADER

    def test_lowercase_and_padding_accepted(self):
        assert classify_line("dck:") is LineType.SECTION_HEADER
        assert classify_line("  DCK:  ") is LineType.SECTION_HEADER

    def test_dck_with_trailing_card_is_not_a_header(self):
        assert not is_deck_header("DCK: 4 Lightning Bolt")
        assert classify_line("DCK: 4 Lightning Bolt") is LineType.COMMENT

    def test_indented_cards_beneath_are_mainboard(self):
        buf = Buffer.from_text("DCK:\n    4 Lightning Bolt\n    2 Shock\n")
        assert buf.get_line(0).line_type is LineType.SECTION_HEADER
        assert buf.get_line(1).line_type is LineType.CARD_ENTRY
        assert buf.card_name_at(1) == "Lightning Bolt"
        assert buf.quantity_at(2) == 2


class TestParsing:
    def test_dck_header_is_structural_not_a_comment(self):
        deck = parse_deck_text("DCK:\n    4 Lightning Bolt\n")
        assert not deck.comments
        assert len(deck.entries) == 1
        assert deck.entries[0].section == DeckSection.MAIN

    def test_full_zone_layout_parses(self):
        deck = parse_deck_text(
            "CMD: 1 Atraxa\n\nDCK:\n    1 Cultivate\n    1 Sol Ring\n\n"
            "SB: 1 Opt\n"
        )
        assert [e.card_name for e in deck.mainboard()] == [
            "Cultivate", "Sol Ring",
        ]
        assert deck.commanders()[0].card_name == "Atraxa"


class TestZoneMoves:
    def test_md_lands_under_dck_header_when_main_is_empty(self):
        buf = Buffer.from_text("DCK:\n\nSB: 4 Lightning Bolt\n")
        result = move_to_zone(buf, Cursor(row=2), LineType.CARD_ENTRY)
        assert result.moved
        lines = result.buffer.to_text().splitlines()
        # Inside the block the moved card is written indented, block-style
        assert lines.index("DCK:") + 1 == lines.index("    4 Lightning Bolt")

    def test_md_appends_to_existing_dck_block(self):
        buf = Buffer.from_text("DCK:\n    4 Shock\n\nSB: 4 Lightning Bolt\n")
        result = move_to_zone(buf, Cursor(row=3), LineType.CARD_ENTRY)
        lines = result.buffer.to_text().splitlines()
        assert (
            lines.index("    4 Lightning Bolt") == lines.index("    4 Shock") + 1
        )


class TestNormalization:
    def test_empty_dck_header_is_dropped(self):
        buf = Buffer.from_text("DCK:\n\n// Sideboard\nSB: 1 Opt\n")
        cleaned = normalize_sections(buf)
        assert "DCK:" not in cleaned.to_text()

    def test_dck_header_with_cards_is_kept(self):
        buf = Buffer.from_text("DCK:\n    4 Shock\n")
        cleaned = normalize_sections(buf)
        assert "DCK:" in cleaned.to_text()

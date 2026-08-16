"""Python-style zone blocks: CMD:/CMP:/SB:/MB: headers with indented cards."""

from __future__ import annotations

from vimtg.data.deck_repository import parse_deck_text, serialize_deck
from vimtg.domain.deck import DeckSection
from vimtg.domain.validation import validate_deck
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.cursor import Cursor
from vimtg.editor.operators import move_to_zone

_BLOCK_COMMANDER = (
    "// Format: commander\n"
    "\n"
    "CMD:\n"
    "    1 Atraxa, Praetors' Voice\n"
    "\n"
    "99 Forest\n"
)

_BLOCK_PARTNERS = (
    "CMD:\n"
    "    1 Thrasios, Triton Hero\n"
    "    1 Tymna the Weaver\n"
    "\n"
    "98 Forest\n"
)


class TestBufferClassification:
    def test_indented_card_under_cmd_is_commander(self):
        buf = Buffer.from_text(_BLOCK_COMMANDER)
        assert buf.get_line(2).line_type is LineType.SECTION_HEADER
        assert buf.get_line(3).line_type is LineType.COMMANDER_ENTRY
        assert buf.card_name_at(3) == "Atraxa, Praetors' Voice"

    def test_partner_pair_both_commander(self):
        buf = Buffer.from_text(_BLOCK_PARTNERS)
        assert buf.get_line(1).line_type is LineType.COMMANDER_ENTRY
        assert buf.get_line(2).line_type is LineType.COMMANDER_ENTRY

    def test_unindented_card_ends_the_block(self):
        buf = Buffer.from_text("CMD:\n    1 Atraxa\n1 Cultivate\n")
        assert buf.get_line(1).line_type is LineType.COMMANDER_ENTRY
        assert buf.get_line(2).line_type is LineType.CARD_ENTRY

    def test_blank_lines_are_neutral_inside_a_block(self):
        buf = Buffer.from_text("CMD:\n    1 Thrasios\n\n    1 Tymna\n")
        assert buf.get_line(3).line_type is LineType.COMMANDER_ENTRY

    def test_explicit_prefix_wins_over_block(self):
        buf = Buffer.from_text("CMD:\n    SB: 1 Opt\n")
        assert buf.get_line(1).line_type is LineType.SIDEBOARD_ENTRY

    def test_indented_card_without_block_is_mainboard(self):
        buf = Buffer.from_text("    4 Lightning Bolt\n")
        assert buf.get_line(0).line_type is LineType.CARD_ENTRY

    def test_cmp_and_sb_blocks(self):
        buf = Buffer.from_text("CMP:\n    1 Lurrus\n\nSB:\n    2 Duress\n")
        assert buf.get_line(1).line_type is LineType.COMPANION_ENTRY
        assert buf.get_line(4).line_type is LineType.SIDEBOARD_ENTRY

    def test_edit_reclassifies_the_block(self):
        buf = Buffer.from_text("CMD:\n    1 Atraxa\n")
        # Turning the header into a comment demotes the card to mainboard
        edited = buf.set_line(0, "// gone")
        assert edited.get_line(1).line_type is LineType.CARD_ENTRY

    def test_quantity_edit_keeps_indentation(self):
        buf = Buffer.from_text("CMD:\n    1 Atraxa\n")
        buf = buf.set_quantity(1, 2)
        assert buf.get_line(1).text == "    2 Atraxa"
        assert buf.get_line(1).line_type is LineType.COMMANDER_ENTRY


class TestParsing:
    def test_block_commander_parses_as_commander_section(self):
        deck = parse_deck_text(_BLOCK_COMMANDER)
        assert [e.card_name for e in deck.commanders()] == [
            "Atraxa, Praetors' Voice",
        ]
        assert len(deck.mainboard()) == 1

    def test_partner_block_parses_both(self):
        deck = parse_deck_text(_BLOCK_PARTNERS)
        assert [e.card_name for e in deck.commanders()] == [
            "Thrasios, Triton Hero", "Tymna the Weaver",
        ]

    def test_block_commander_validates_as_commander_deck(self):
        deck = parse_deck_text(_BLOCK_COMMANDER)
        errors = validate_deck(deck, fmt="commander")
        assert not any("No commander" in e.message for e in errors)
        assert not any("requires exactly" in e.message for e in errors)

    def test_serialize_canonicalizes_to_prefix_style(self):
        deck = parse_deck_text(_BLOCK_PARTNERS)
        out = serialize_deck(deck)
        assert "CMD: 1 Thrasios, Triton Hero" in out
        assert "CMD: 1 Tymna the Weaver" in out
        # And the canonical form round-trips
        again = parse_deck_text(out)
        assert len(again.commanders()) == 2

    def test_sb_block_parses_as_sideboard(self):
        deck = parse_deck_text("4 Bolt\n\nSB:\n    2 Duress\n")
        assert deck.sideboard()[0].card_name == "Duress"
        assert deck.sideboard()[0].section == DeckSection.SIDEBOARD


class TestZoneMovesIntoBlocks:
    def test_mc_appends_indented_into_cmd_block(self):
        buf = Buffer.from_text(
            "CMD:\n    1 Thrasios, Triton Hero\n\n1 Tymna the Weaver\n"
        )
        result = move_to_zone(buf, Cursor(row=3), LineType.COMMANDER_ENTRY)
        assert result.moved
        lines = result.buffer.to_text().splitlines()
        assert lines[2] == "    1 Tymna the Weaver"
        assert result.buffer.get_line(2).line_type is LineType.COMMANDER_ENTRY

    def test_mc_lands_under_empty_cmd_header(self):
        buf = Buffer.from_text("CMD:\n\n1 Atraxa\n1 Forest\n")
        result = move_to_zone(buf, Cursor(row=2), LineType.COMMANDER_ENTRY)
        lines = result.buffer.to_text().splitlines()
        assert lines[1] == "    1 Atraxa"
        assert result.buffer.get_line(1).line_type is LineType.COMMANDER_ENTRY

    def test_mc_without_block_still_writes_prefix_style(self):
        buf = Buffer.from_text("1 Atraxa\n1 Forest\n")
        result = move_to_zone(buf, Cursor(row=0), LineType.COMMANDER_ENTRY)
        assert "CMD: 1 Atraxa" in result.buffer.to_text()


class TestLayoutRegroup:
    def test_regroup_preserves_block_commander_zone(self):
        from vimtg.editor.layout import LAYOUT_CATEGORY, regroup_buffer

        buf = Buffer.from_text(_BLOCK_PARTNERS)
        regrouped = regroup_buffer(buf, LAYOUT_CATEGORY)
        text = regrouped.to_text()
        assert "CMD: 1 Thrasios, Triton Hero" in text
        assert "CMD: 1 Tymna the Weaver" in text
        commanders = [
            i for i in range(regrouped.line_count())
            if regrouped.get_line(i).line_type is LineType.COMMANDER_ENTRY
        ]
        assert len(commanders) == 2

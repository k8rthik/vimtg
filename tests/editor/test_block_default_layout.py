"""Block style is the default layout: new zones open as blocks, empty
type headers are cleaned zone-aware, new decks scaffold a DCK: body."""

from __future__ import annotations

from vimtg.data.deck_repository import DeckRepository
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.cursor import Cursor
from vimtg.editor.operators import move_to_zone
from vimtg.editor.sections import normalize_sections
from vimtg.services.deck_service import (
    DeckService,
    scaffold_deck_body,
    scaffold_missing_metadata,
)


class TestMcLeavesNoEmptyTypeHeader:
    """Regression: making the only creature the commander left '// Creature'."""

    def test_empty_type_section_is_dropped_after_mc(self):
        buf = Buffer.from_text(
            "// Deck: T\n// Format: commander\n\n"
            "// Creature\n1 Atraxa, Praetors' Voice\n\n"
            "// Land\n30 Forest\n"
        )
        result = move_to_zone(buf, Cursor(row=4), LineType.COMMANDER_ENTRY)
        cleaned = normalize_sections(result.buffer)
        text = cleaned.to_text()
        assert "// Creature" not in text
        assert "// Land" in text  # occupied sections stay
        lines = text.splitlines()
        assert lines.index("CMD:") + 1 == lines.index(
            "    1 Atraxa, Praetors' Voice"
        )

    def test_commander_line_does_not_keep_foreign_header_alive(self):
        # A '// Creature' header whose extent holds only a CMD: line is
        # empty — the section runs to the next header, and a foreign-zone
        # line inside it is not one of its cards
        buf = Buffer.from_text(
            "// Creature\n\nCMD: 1 Atraxa\n\n// Lands\n1 Forest\n"
        )
        cleaned = normalize_sections(buf)
        assert "// Creature" not in cleaned.to_text()
        assert "// Lands" in cleaned.to_text()

    def test_mainboard_card_after_foreign_line_keeps_header(self):
        # Same extent rule the other way: a mainboard card anywhere in
        # the section's extent occupies it, even past a CMD: line
        buf = Buffer.from_text("// Creature\n\nCMD: 1 Atraxa\n1 Forest\n")
        cleaned = normalize_sections(buf)
        assert "// Creature" in cleaned.to_text()

    def test_sideboard_header_kept_by_sideboard_cards(self):
        buf = Buffer.from_text("4 Bolt\n\n// Sideboard\nSB: 1 Duress\n")
        cleaned = normalize_sections(buf)
        assert "// Sideboard" in cleaned.to_text()


class TestScaffoldDeckBody:
    def test_empty_commander_deck_gets_cmd_and_dck(self):
        text = scaffold_deck_body(
            scaffold_missing_metadata("// Format: commander\n")
        )
        lines = text.splitlines()
        assert "CMD:" in lines
        assert "DCK:" in lines
        assert lines.index("CMD:") < lines.index("DCK:")

    def test_empty_other_format_gets_dck_only(self):
        text = scaffold_deck_body(
            scaffold_missing_metadata("// Format: modern\n")
        )
        assert "DCK:" in text.splitlines()
        assert "CMD:" not in text.splitlines()

    def test_deck_with_cards_is_untouched(self):
        text = "// Deck: X\n\n4 Bolt\n"
        assert scaffold_deck_body(text) is text

    def test_deck_with_zone_headers_is_untouched(self):
        text = "// Deck: X\n\nDCK:\n"
        assert scaffold_deck_body(text) is text

    def test_scaffolded_body_survives_normalization(self):
        # An empty DCK:/CMD: must not be cleaned away on the first sync
        text = scaffold_deck_body(
            scaffold_missing_metadata("// Format: commander\n")
        )
        cleaned = normalize_sections(Buffer.from_text(text))
        assert "DCK:" in cleaned.to_text()
        assert "CMD:" in cleaned.to_text()

    def test_new_deck_template_uses_blocks(self):
        service = DeckService(deck_repo=DeckRepository())
        text = service.new_deck("My Deck", fmt="commander")
        lines = text.splitlines()
        assert "CMD:" in lines
        assert "DCK:" in lines
        assert "// Mainboard" not in lines

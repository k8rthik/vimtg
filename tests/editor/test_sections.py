"""Tests for section normalization (empty-header removal, blank collapsing)."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.sections import normalize_sections


class TestNormalizeSections:
    def test_clean_buffer_returns_same_object(self) -> None:
        buf = Buffer.from_text("// Creatures\n4 Goblin Guide\n\n// Lands\n20 Mountain\n")
        assert normalize_sections(buf) is buf

    def test_removes_empty_section_header(self) -> None:
        buf = Buffer.from_text("// Creatures\n\n// Lands\n20 Mountain\n")
        cleaned = normalize_sections(buf)
        assert cleaned.to_text() == "// Lands\n20 Mountain\n"

    def test_keeps_section_with_cards_after_blank(self) -> None:
        buf = Buffer.from_text("// Creatures\n\n4 Goblin Guide\n")
        cleaned = normalize_sections(buf)
        assert "// Creatures" in cleaned.to_text()

    def test_collapses_consecutive_blanks(self) -> None:
        buf = Buffer.from_text("4 Goblin Guide\n\n\n\n4 Lightning Bolt\n")
        cleaned = normalize_sections(buf)
        assert cleaned.to_text() == "4 Goblin Guide\n\n4 Lightning Bolt\n"

    def test_pads_blank_before_header(self) -> None:
        buf = Buffer.from_text("4 Goblin Guide\n// Lands\n20 Mountain\n")
        cleaned = normalize_sections(buf)
        assert cleaned.to_text() == "4 Goblin Guide\n\n// Lands\n20 Mountain\n"

    def test_no_padding_after_metadata(self) -> None:
        buf = Buffer.from_text("// Deck: Burn\n// Creatures\n4 Goblin Guide\n")
        cleaned = normalize_sections(buf)
        assert cleaned.to_text() == "// Deck: Burn\n// Creatures\n4 Goblin Guide\n"

    def test_empty_buffer_unchanged(self) -> None:
        buf = Buffer.from_text("\n")
        assert normalize_sections(buf) is buf

    def test_idempotent(self) -> None:
        buf = Buffer.from_text("// Creatures\n\n// Lands\n\n\n20 Mountain\n// Spells\n")
        once = normalize_sections(buf)
        assert normalize_sections(once) is once


class TestMaybeboardSections:
    def test_header_with_only_maybeboard_cards_survives(self) -> None:
        """A section whose cards are all MB: lines is not empty (regression:
        the card-type set was a stale copy missing MAYBEBOARD_ENTRY)."""
        buf = Buffer.from_text("// Maybeboard\nMB: 2 Opt\nMB: 1 Shock\n")
        cleaned = normalize_sections(buf)
        assert "// Maybeboard" in cleaned.to_text()
        assert "MB: 2 Opt" in cleaned.to_text()

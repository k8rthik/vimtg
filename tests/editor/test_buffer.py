"""Tests for the editor Buffer and line classification."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.editor.buffer import (
    Buffer,
    LineType,
    classify_line,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_text() -> str:
    return (FIXTURES_DIR / "sample_burn.deck").read_text()


@pytest.fixture
def sample_buffer(sample_text: str) -> Buffer:
    return Buffer.from_text(sample_text)


# --- classify_line tests ---


class TestClassifyLine:
    def test_blank(self) -> None:
        assert classify_line("") == LineType.BLANK
        assert classify_line("   ") == LineType.BLANK

    def test_comment(self) -> None:
        assert classify_line("// just a comment") == LineType.COMMENT

    def test_section_header(self) -> None:
        assert classify_line("// Creature") == LineType.SECTION_HEADER
        assert classify_line("// Land") == LineType.SECTION_HEADER
        assert classify_line("// Sideboard") == LineType.SECTION_HEADER

    def test_plural_headers_are_section_headers(self) -> None:
        assert classify_line("// Creatures") == LineType.SECTION_HEADER
        assert classify_line("// Lands") == LineType.SECTION_HEADER
        assert classify_line("// Spells") == LineType.SECTION_HEADER

    def test_metadata(self) -> None:
        assert classify_line("// Deck: Burn") == LineType.METADATA
        assert classify_line("// Format: modern") == LineType.METADATA
        assert classify_line("// Author: test") == LineType.METADATA

    def test_card_entry(self) -> None:
        assert classify_line("4 Lightning Bolt") == LineType.CARD_ENTRY
        assert classify_line("  2 Shard Volley  ") == LineType.CARD_ENTRY

    def test_sideboard_entry(self) -> None:
        assert classify_line("SB: 2 Rest in Peace") == LineType.SIDEBOARD_ENTRY

    def test_commander_entry(self) -> None:
        assert classify_line("CMD: 1 Kenrith, the Returned King") == LineType.COMMANDER_ENTRY

    def test_fallback_to_comment(self) -> None:
        # Non-numeric, non-comment text falls back to comment
        assert classify_line("some random text") == LineType.COMMENT


# --- Buffer.from_text / to_text tests ---


class TestBufferFromText:
    def test_from_text_line_count(self, sample_buffer: Buffer) -> None:
        # sample_burn.deck has 35 lines of content (including blanks)
        assert sample_buffer.line_count() == 35

    def test_to_text_roundtrip(self, sample_text: str) -> None:
        buf = Buffer.from_text(sample_text)
        assert buf.to_text() == sample_text

    def test_empty_buffer(self) -> None:
        buf = Buffer.from_text("")
        # Empty text yields one blank line so to_text() round-trips
        assert buf.line_count() == 1
        assert Buffer.from_text(buf.to_text()).line_count() == 1

    def test_single_line(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        assert buf.line_count() == 1
        assert buf.get_line(0).line_type == LineType.CARD_ENTRY


# --- Mutation methods ---


class TestBufferMutations:
    def test_set_line_returns_new(self, sample_buffer: Buffer) -> None:
        original_text = sample_buffer.get_line(5).text
        new_buf = sample_buffer.set_line(5, "3 New Card")
        # Original unchanged
        assert sample_buffer.get_line(5).text == original_text
        # New buffer has the change
        assert new_buf.get_line(5).text == "3 New Card"
        assert new_buf.get_line(5).line_type == LineType.CARD_ENTRY

    def test_insert_line(self, sample_buffer: Buffer) -> None:
        original_count = sample_buffer.line_count()
        new_buf = sample_buffer.insert_line(2, "// new comment")
        assert new_buf.line_count() == original_count + 1
        assert new_buf.get_line(2).text == "// new comment"
        # Original unchanged
        assert sample_buffer.line_count() == original_count

    def test_delete_lines(self, sample_buffer: Buffer) -> None:
        original_count = sample_buffer.line_count()
        new_buf, deleted = sample_buffer.delete_lines(5, 7)
        assert new_buf.line_count() == original_count - 3
        assert len(deleted) == 3
        # Original unchanged
        assert sample_buffer.line_count() == original_count

    def test_delete_all_lines_leaves_blank(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        new_buf, deleted = buf.delete_lines(0, 0)
        assert new_buf.line_count() == 1
        assert new_buf.get_line(0).line_type == LineType.BLANK
        assert deleted == ("4 Lightning Bolt",)

    def test_delete_lines_end_out_of_bounds_clamped(self) -> None:
        buf = Buffer.from_text("1 Bolt\n2 Guide\n3 Spike\n")
        new_buf, deleted = buf.delete_lines(1, 99)
        assert new_buf.line_count() == 1
        assert new_buf.get_line(0).text == "1 Bolt"
        assert deleted == ("2 Guide", "3 Spike")

    def test_delete_lines_start_out_of_bounds_noop(self) -> None:
        buf = Buffer.from_text("1 Bolt\n2 Guide\n")
        new_buf, deleted = buf.delete_lines(5, 9)
        # Start clamps to last line; deletes just that line rather than crashing.
        assert deleted == ("2 Guide",)
        assert new_buf.line_count() == 1

    def test_delete_lines_reversed_range_noop(self) -> None:
        buf = Buffer.from_text("1 Bolt\n2 Guide\n")
        new_buf, deleted = buf.delete_lines(1, 0)
        assert deleted == ()
        assert new_buf.line_count() == 2

    def test_append_line(self, sample_buffer: Buffer) -> None:
        original_count = sample_buffer.line_count()
        new_buf = sample_buffer.append_line("1 New Card")
        assert new_buf.line_count() == original_count + 1
        assert new_buf.get_line(new_buf.line_count() - 1).text == "1 New Card"


# --- Card extraction methods ---


class TestCardExtraction:
    def test_card_name_at(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        assert buf.card_name_at(0) == "Lightning Bolt"

    def test_card_name_at_sideboard(self) -> None:
        buf = Buffer.from_text("SB: 2 Rest in Peace\n")
        assert buf.card_name_at(0) == "Rest in Peace"

    def test_card_name_at_commander(self) -> None:
        buf = Buffer.from_text("CMD: 1 Kenrith, the Returned King\n")
        assert buf.card_name_at(0) == "Kenrith, the Returned King"

    def test_card_name_at_non_card(self) -> None:
        buf = Buffer.from_text("// Creature\n")
        assert buf.card_name_at(0) is None

    def test_card_name_at_out_of_bounds(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        assert buf.card_name_at(-1) is None
        assert buf.card_name_at(5) is None

    def test_quantity_at(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        assert buf.quantity_at(0) == 4

    def test_quantity_at_sideboard(self) -> None:
        buf = Buffer.from_text("SB: 2 Rest in Peace\n")
        assert buf.quantity_at(0) == 2

    def test_quantity_at_non_card(self) -> None:
        buf = Buffer.from_text("// comment\n")
        assert buf.quantity_at(0) is None


# --- Navigation helpers ---


class TestNavigation:
    def test_is_card_line(self) -> None:
        buf = Buffer.from_text("// comment\n4 Lightning Bolt\n\nSB: 2 Rest in Peace\n")
        assert buf.is_card_line(0) is False  # comment
        assert buf.is_card_line(1) is True   # card
        assert buf.is_card_line(2) is False  # blank
        assert buf.is_card_line(3) is True   # sideboard

    def test_is_card_line_out_of_bounds(self) -> None:
        buf = Buffer.from_text("4 Lightning Bolt\n")
        assert buf.is_card_line(-1) is False
        assert buf.is_card_line(99) is False

    def test_next_card_line(self, sample_buffer: Buffer) -> None:
        # Line 0 is "// Deck: Burn" (metadata), first card line should be found
        result = sample_buffer.next_card_line(0)
        assert result is not None
        assert sample_buffer.is_card_line(result)

    def test_next_card_line_skips_blanks_and_comments(self) -> None:
        buf = Buffer.from_text("4 Bolt\n// comment\n\n2 Spike\n")
        assert buf.next_card_line(0) == 3  # skips comment and blank

    def test_prev_card_line(self) -> None:
        buf = Buffer.from_text("4 Bolt\n// comment\n\n2 Spike\n")
        assert buf.prev_card_line(3) == 0  # goes back to first card

    def test_next_card_line_at_end(self, sample_buffer: Buffer) -> None:
        last = sample_buffer.line_count() - 1
        assert sample_buffer.next_card_line(last) is None

    def test_prev_card_line_at_start(self, sample_buffer: Buffer) -> None:
        assert sample_buffer.prev_card_line(0) is None

    def test_section_range(self) -> None:
        text = "// Header\n4 Bolt\n4 Spike\n4 Blaze\n\n// Another\n2 Mountain\n"
        buf = Buffer.from_text(text)
        result = buf.section_range(2)  # middle of first card section
        assert result == (1, 3)

    def test_section_range_non_card(self) -> None:
        buf = Buffer.from_text("// comment\n4 Bolt\n")
        assert buf.section_range(0) is None


class TestSetQuantity:
    def test_plain_card(self) -> None:
        buf = Buffer.from_text("4 Goblin Guide\n")
        assert buf.set_quantity(0, 2).get_line(0).text == "2 Goblin Guide"

    def test_preserves_tags(self) -> None:
        buf = Buffer.from_text("4 Goblin Guide  #core #aggro\n")
        assert buf.set_quantity(0, 1).get_line(0).text == "1 Goblin Guide  #core #aggro"

    def test_preserves_sideboard_prefix(self) -> None:
        buf = Buffer.from_text("SB: 2 Rest in Peace\n")
        assert buf.set_quantity(0, 3).get_line(0).text == "SB: 3 Rest in Peace"

    def test_preserves_commander_prefix(self) -> None:
        buf = Buffer.from_text("CMD: 1 Atraxa\n")
        assert buf.set_quantity(0, 1).get_line(0).text == "CMD: 1 Atraxa"

    def test_name_starting_with_digit(self) -> None:
        buf = Buffer.from_text("4 7 Wonders\n")
        assert buf.set_quantity(0, 2).get_line(0).text == "2 7 Wonders"

    def test_non_card_line_unchanged(self) -> None:
        buf = Buffer.from_text("// comment\n")
        assert buf.set_quantity(0, 5).get_line(0).text == "// comment"


class TestTagCounts:
    def test_empty_buffer(self) -> None:
        assert Buffer.from_text("4 Goblin Guide\n").tag_counts() == {}

    def test_counts_across_lines(self) -> None:
        buf = Buffer.from_text(
            "4 Goblin Guide  #core\n4 Lightning Bolt  #core #burn\n2 Skullcrack  #burn\n"
        )
        assert buf.tag_counts() == {"core": 2, "burn": 2}

    def test_ignores_non_card_lines(self) -> None:
        buf = Buffer.from_text("// Comment  #core\n4 Goblin Guide  #flex\n")
        assert buf.tag_counts() == {"flex": 1}


class TestMetadataClassification:
    def test_empty_value_is_metadata(self):
        assert classify_line("// Format:") == LineType.METADATA

    def test_space_before_colon_is_metadata(self):
        assert classify_line("// Format : modern") == LineType.METADATA

    def test_source_key_is_metadata(self):
        assert classify_line("// Source: https://x.com") == LineType.METADATA

    def test_unknown_key_is_comment(self):
        assert classify_line("// Wincons: storm") == LineType.COMMENT


class TestCardComments:
    def _buf(self, text):
        return Buffer.from_text(text)

    def test_comment_at_none(self):
        buf = self._buf("4 Lightning Bolt\n")
        assert buf.comment_at(0) == ""

    def test_comment_at_present(self):
        buf = self._buf("4 Lightning Bolt  // wincon\n")
        assert buf.comment_at(0) == "wincon"

    def test_comment_at_non_card_line(self):
        buf = self._buf("// a comment  // not a card\n")
        assert buf.comment_at(0) == ""

    def test_set_comment_adds(self):
        buf = self._buf("4 Bolt\n").set_comment(0, "wincon")
        assert buf.get_line(0).text == "4 Bolt  // wincon"

    def test_set_comment_replaces(self):
        buf = self._buf("4 Bolt  // old\n").set_comment(0, "new")
        assert buf.get_line(0).text == "4 Bolt  // new"

    def test_set_comment_empty_removes(self):
        buf = self._buf("4 Bolt  // old\n").set_comment(0, "")
        assert buf.get_line(0).text == "4 Bolt"

    def test_set_comment_non_card_noop(self):
        buf = self._buf("// header\n")
        assert buf.set_comment(0, "x") is buf

    def test_set_comment_preserves_tags(self):
        buf = self._buf("4 Bolt  #burn\n").set_comment(0, "wincon")
        assert buf.get_line(0).text == "4 Bolt  #burn  // wincon"

    def test_card_name_at_strips_comment(self):
        buf = self._buf("SB: 2 Pyroblast  // vs blue\n")
        assert buf.card_name_at(0) == "Pyroblast"

    def test_tags_at_ignores_hash_in_comment(self):
        buf = self._buf("4 Bolt  // see #discussion\n")
        assert buf.tags_at(0) == frozenset()

    def test_tags_at_with_tags_and_comment(self):
        buf = self._buf("4 Bolt  #burn  // wincon\n")
        assert buf.tags_at(0) == frozenset({"burn"})

    def test_set_tags_preserves_comment(self):
        buf = self._buf("4 Bolt  #burn  // wincon\n")
        buf = buf.set_tags(0, frozenset({"core"}))
        assert buf.get_line(0).text == "4 Bolt  #core  // wincon"

    def test_set_quantity_preserves_comment(self):
        buf = self._buf("4 Bolt  #burn  // wincon\n").set_quantity(0, 2)
        assert buf.get_line(0).text == "2 Bolt  #burn  // wincon"

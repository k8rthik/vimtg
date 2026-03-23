"""Tests for vimtg.editor.text_objects — vim-style text objects for decks."""

from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.text_objects import (
    TEXT_OBJECT_REGISTRY,
    text_object_around_card,
    text_object_around_section,
    text_object_inner_card,
    text_object_inner_section,
)

# Line indices:
# 0: // Creatures        (SECTION_HEADER)
# 1: 4 Ragavan...        (CARD_ENTRY)
# 2: 2 Dragon's Rage...  (CARD_ENTRY)
# 3:                      (BLANK)
# 4: // Spells            (SECTION_HEADER)
# 5: 4 Lightning Bolt    (CARD_ENTRY)
# 6: 3 Unholy Heat       (CARD_ENTRY)
# 7:                      (BLANK)
# 8: // Sideboard         (COMMENT)
# 9: SB: 2 Engineered... (SIDEBOARD_ENTRY)
SAMPLE_DECK = """\
// Creatures
4 Ragavan, Nimble Pilferer
2 Dragon's Rage Channeler

// Spells
4 Lightning Bolt
3 Unholy Heat

// Sideboard
SB: 2 Engineered Explosives"""


def _buf() -> Buffer:
    return Buffer.from_text(SAMPLE_DECK)


def _cur(row: int) -> Cursor:
    return Cursor(row=row)


class TestInnerCard:
    def test_inner_card(self) -> None:
        result = text_object_inner_card(_cur(1), _buf())
        assert result == (1, 1)

    def test_inner_card_on_comment(self) -> None:
        result = text_object_inner_card(_cur(0), _buf())
        assert result is None

    def test_inner_card_on_blank(self) -> None:
        result = text_object_inner_card(_cur(3), _buf())
        assert result is None

    def test_inner_card_sideboard(self) -> None:
        result = text_object_inner_card(_cur(9), _buf())
        assert result == (9, 9)


class TestAroundCard:
    def test_around_card(self) -> None:
        result = text_object_around_card(_cur(1), _buf())
        assert result == (1, 1)

    def test_around_card_on_comment(self) -> None:
        result = text_object_around_card(_cur(0), _buf())
        assert result is None


class TestInnerSection:
    def test_inner_section(self) -> None:
        """ip on a card line returns the contiguous card block."""
        result = text_object_inner_section(_cur(1), _buf())
        assert result == (1, 2)

    def test_inner_section_spells(self) -> None:
        result = text_object_inner_section(_cur(5), _buf())
        assert result == (5, 6)

    def test_inner_section_at_start(self) -> None:
        """ip on the first card of a section."""
        result = text_object_inner_section(_cur(1), _buf())
        assert result is not None
        assert result[0] == 1

    def test_inner_section_at_end(self) -> None:
        """ip on the last card of a section."""
        result = text_object_inner_section(_cur(2), _buf())
        assert result == (1, 2)

    def test_inner_section_on_header_finds_next(self) -> None:
        """ip on a section header searches down for nearest card block."""
        result = text_object_inner_section(_cur(0), _buf())
        assert result == (1, 2)

    def test_inner_section_single_card(self) -> None:
        """ip on a single-card section returns that one line."""
        result = text_object_inner_section(_cur(9), _buf())
        assert result == (9, 9)

    def test_inner_section_on_blank_finds_next(self) -> None:
        """ip on a blank line searches forward."""
        result = text_object_inner_section(_cur(3), _buf())
        # Blank at line 3, next card block starts at 5
        assert result == (5, 6)


class TestAroundSection:
    def test_around_section_with_header(self) -> None:
        """ap includes the section header above and trailing blank below."""
        result = text_object_around_section(_cur(1), _buf())
        # Header at 0, cards at 1-2, blank at 3
        assert result == (0, 3)

    def test_around_section_spells(self) -> None:
        result = text_object_around_section(_cur(5), _buf())
        # Header at 4, cards at 5-6, blank at 7
        assert result == (4, 7)

    def test_around_section_last_section_no_trailing_blank(self) -> None:
        """ap at the end of file without a trailing blank."""
        result = text_object_around_section(_cur(9), _buf())
        # Header/comment at 8, card at 9, no blank after
        assert result == (8, 9)

    def test_around_section_on_header(self) -> None:
        """ap on a section header still works via inner search."""
        result = text_object_around_section(_cur(4), _buf())
        assert result == (4, 7)

    def test_around_section_no_cards_returns_none(self) -> None:
        """ap on a buffer with no card lines returns None."""
        buf = Buffer.from_text("// Just a comment\n// Another comment")
        result = text_object_around_section(Cursor(row=0), buf)
        assert result is None


class TestRegistry:
    def test_registry_keys(self) -> None:
        assert set(TEXT_OBJECT_REGISTRY.keys()) == {"iw", "aw", "ip", "ap"}

    def test_registry_iw_callable(self) -> None:
        fn = TEXT_OBJECT_REGISTRY["iw"]
        result = fn(_cur(1), _buf())
        assert result == (1, 1)

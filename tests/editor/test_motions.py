"""Tests for vim-style motions on a deck buffer."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.motions import (
    MOTION_REGISTRY,
    VIEW_MOTIONS,
    motion_down,
    motion_first_line,
    motion_goto_line,
    motion_half_page_down,
    motion_half_page_up,
    motion_last_line,
    motion_next_card,
    motion_next_section,
    motion_prev_card,
    motion_prev_section,
    motion_up,
    motion_view_bottom,
    motion_view_middle,
    motion_view_top,
)

# A deck-like buffer for testing motions
DECK_TEXT = """\
// Deck: Test
// Format: standard

// Creature
4 Goblin Guide
4 Monastery Swiftspear

// Instant
4 Lightning Bolt
4 Lava Spike

// Land
4 Mountain
"""


def _buf() -> Buffer:
    return Buffer.from_text(DECK_TEXT)


class TestBasicMotions:
    def test_down(self) -> None:
        buf = _buf()
        c = Cursor(row=0)
        result = motion_down(c, buf)
        assert result.row == 1

    def test_down_count(self) -> None:
        buf = _buf()
        c = Cursor(row=0)
        # count=3 skips blank lines: row 0→1→3(skip 2 blank)→4
        result = motion_down(c, buf, count=3)
        assert result.row == 4

    def test_down_at_bottom(self) -> None:
        buf = _buf()
        last = buf.line_count() - 1
        c = Cursor(row=last)
        result = motion_down(c, buf)
        assert result.row == last

    def test_up(self) -> None:
        buf = _buf()
        c = Cursor(row=5)
        result = motion_up(c, buf)
        assert result.row == 4

    def test_up_count(self) -> None:
        buf = _buf()
        c = Cursor(row=5)
        # count=3 skips blank lines: row 5→4→3→1(skip 2 blank)
        result = motion_up(c, buf, count=3)
        assert result.row == 1

    def test_up_at_top(self) -> None:
        buf = _buf()
        c = Cursor(row=0)
        result = motion_up(c, buf)
        assert result.row == 0


class TestLineMotions:
    def test_first_line(self) -> None:
        buf = _buf()
        c = Cursor(row=5, col=3)
        result = motion_first_line(c, buf)
        assert result.row == 0
        assert result.col == 0

    def test_last_line(self) -> None:
        buf = _buf()
        c = Cursor(row=0)
        result = motion_last_line(c, buf)
        assert result.row == buf.line_count() - 1

    def test_goto_line(self) -> None:
        buf = _buf()
        c = Cursor(row=0)
        # goto line 5 (1-indexed count=5 -> row 4)
        result = motion_goto_line(c, buf, count=5)
        assert result.row == 4

    def test_goto_line_beyond_end(self) -> None:
        buf = _buf()
        c = Cursor(row=0)
        result = motion_goto_line(c, buf, count=9999)
        assert result.row == buf.line_count() - 1


class TestCardMotions:
    def test_next_card(self) -> None:
        buf = _buf()
        # Start at "// Deck: Test" (line 0), next card should be "4 Goblin Guide" (line 4)
        c = Cursor(row=0)
        result = motion_next_card(c, buf)
        assert buf.is_card_line(result.row)
        assert result.row == 4

    def test_prev_card(self) -> None:
        buf = _buf()
        # Start at "4 Monastery Swiftspear" (line 5), prev card should be "4 Goblin Guide" (line 4)
        c = Cursor(row=5)
        result = motion_prev_card(c, buf)
        assert result.row == 4

    def test_next_card_at_end(self) -> None:
        buf = _buf()
        # Start at last card line "4 Mountain" (line 12)
        c = Cursor(row=12)
        result = motion_next_card(c, buf)
        assert result.row == 12  # stays put

    def test_prev_card_at_start(self) -> None:
        buf = _buf()
        # Start at first card "4 Goblin Guide" (line 4)
        c = Cursor(row=4)
        result = motion_prev_card(c, buf)
        assert result.row == 4  # stays put (no card before)

    def test_next_card_multiple(self) -> None:
        buf = _buf()
        c = Cursor(row=4)  # "4 Goblin Guide"
        result = motion_next_card(c, buf, count=2)
        assert result.row == 8  # skips to "4 Lightning Bolt" (past blank + header)


class TestSectionMotions:
    def test_next_section(self) -> None:
        buf = _buf()
        c = Cursor(row=4)  # "4 Goblin Guide" in Creature
        result = motion_next_section(c, buf)
        # Should jump to first card of Instant section: "4 Lightning Bolt" (line 8)
        assert result.row == 8

    def test_prev_section(self) -> None:
        buf = _buf()
        c = Cursor(row=8)  # "4 Lightning Bolt" in Instant
        result = motion_prev_section(c, buf)
        # Should jump to first card of Creature section: "4 Goblin Guide" (line 4)
        assert result.row == 4

    def test_next_section_at_last_section(self) -> None:
        buf = _buf()
        c = Cursor(row=12)  # "4 Mountain" in Land (last section)
        result = motion_next_section(c, buf)
        # Should stay at end or near end
        assert result.row >= 12


class TestHalfPageMotions:
    def test_half_page_down(self) -> None:
        buf = _buf()
        c = Cursor(row=0)
        result = motion_half_page_down(c, buf)
        # Should move 15 but clamp to buffer size
        assert result.row == min(15, buf.line_count() - 1)

    def test_half_page_up(self) -> None:
        buf = _buf()
        c = Cursor(row=10)
        result = motion_half_page_up(c, buf)
        assert result.row == 0  # 10 - 15 = clamped to 0


class TestMotionRegistry:
    def test_registry_has_all_keys(self) -> None:
        expected_keys = {
            "j", "k", "gg", "G",
            "w", "b", "{", "}", "[[", "]]", "ctrl_d", "ctrl_u",
        }
        assert set(MOTION_REGISTRY.keys()) == expected_keys

    def test_registry_functions_callable(self) -> None:
        buf = _buf()
        c = Cursor(row=5)
        for key, fn in MOTION_REGISTRY.items():
            result = fn(c, buf)
            assert isinstance(result, Cursor), f"Motion '{key}' did not return a Cursor"


class TestViewMotions:
    """H / M / L target the band of rows the deck view shows."""

    def test_h_goes_to_band_top(self) -> None:
        assert motion_view_top(Cursor(row=9), _buf(), (4, 9)).row == 4

    def test_h_count_offsets_from_top(self) -> None:
        assert motion_view_top(Cursor(row=9), _buf(), (4, 9), 2).row == 5

    def test_h_skips_blank_lines_downward(self) -> None:
        # row 6 is blank; H lands on the next non-blank line
        assert motion_view_top(Cursor(row=9), _buf(), (6, 12)).row == 7

    def test_h_count_clamps_to_band_bottom(self) -> None:
        assert motion_view_top(Cursor(row=0), _buf(), (3, 5), 99).row == 5

    def test_l_goes_to_band_bottom(self) -> None:
        assert motion_view_bottom(Cursor(row=0), _buf(), (0, 9)).row == 9

    def test_l_count_offsets_from_bottom(self) -> None:
        assert motion_view_bottom(Cursor(row=0), _buf(), (0, 9), 2).row == 8

    def test_l_skips_blank_lines_upward(self) -> None:
        # row 10 is blank; L lands on the line above it
        assert motion_view_bottom(Cursor(row=0), _buf(), (0, 10)).row == 9

    def test_m_goes_to_band_middle(self) -> None:
        assert motion_view_middle(Cursor(row=0), _buf(), (4, 8)).row == 7  # middle row 6 is blank

    def test_m_exact_middle(self) -> None:
        assert motion_view_middle(Cursor(row=0), _buf(), (3, 5)).row == 4

    def test_band_clamped_to_buffer(self) -> None:
        buf = _buf()
        last = buf.line_count() - 1
        result = motion_view_bottom(Cursor(row=0), buf, (0, last + 50))
        assert result.row <= last
        assert motion_view_top(Cursor(row=0), buf, (-5, 3)).row == 0

    def test_all_blank_band_keeps_target(self) -> None:
        buf = Buffer.from_text("\n\n\n")
        assert motion_view_middle(Cursor(row=0), buf, (0, 2)).row == 1

    def test_registry(self) -> None:
        assert set(VIEW_MOTIONS) == {"H", "M", "L"}
        assert not set(VIEW_MOTIONS) & set(MOTION_REGISTRY)

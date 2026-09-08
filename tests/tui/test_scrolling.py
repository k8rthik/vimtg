"""compute_block_scroll_offset — scrolloff for a multi-row cursor block.

The deck view's cursor line renders its own row plus any inline
expansion (rules text) beneath it. The window must keep that whole
block, plus scrolloff rows of context, on screen — and may scroll past
the last line so a block at the end of the buffer still fits.
"""

from vimtg.tui.widgets.scrolling import compute_block_scroll_offset


class TestFits:
    def test_content_shorter_than_viewport_never_scrolls(self) -> None:
        assert compute_block_scroll_offset(
            4, 1, 0, total=5, viewport=10, scrolloff=3, bottom_pad=3
        ) == 0

    def test_block_that_exactly_fills_viewport_does_not_scroll(self) -> None:
        # 5 lines + 5 expansion rows = 10 rows in a 10-row viewport: pad
        # never forces a scroll when everything already fits.
        assert compute_block_scroll_offset(
            4, 6, 0, total=5, viewport=10, scrolloff=3, bottom_pad=3
        ) == 0


class TestScrolloff:
    def test_single_row_matches_plain_scrolloff(self) -> None:
        # 15 lines, viewport 10, scrolloff 2: row 7 fits, row 8 scrolls by 1.
        assert compute_block_scroll_offset(7, 1, 0, total=15, viewport=10, scrolloff=2) == 0
        assert compute_block_scroll_offset(8, 1, 0, total=15, viewport=10, scrolloff=2) == 1

    def test_scrolls_before_cursor_reaches_last_row(self) -> None:
        # Moving down one line at a time: the cursor row never lands on
        # the bottom `scrolloff` rows of the viewport.
        offset = 0
        for row in range(30):
            offset = compute_block_scroll_offset(
                row, 1, offset, total=30, viewport=10, scrolloff=3
            )
            screen_row = row - offset
            assert 0 <= screen_row <= 10 - 1 - 3 or row >= 30 - 3

    def test_expansion_pulls_view_down(self) -> None:
        # Cursor on row 5 with a 4-row expansion (rows 5..8) in a 10-row
        # viewport: block bottom 8 + scrolloff 2 must be < viewport, so
        # scroll by 1.
        assert compute_block_scroll_offset(5, 4, 0, total=30, viewport=10, scrolloff=2) == 1

    def test_top_context_wins_when_block_too_tall(self) -> None:
        # A block taller than the viewport still shows the cursor row
        # with scrolloff above it — the expansion clips, never the cursor.
        off = compute_block_scroll_offset(10, 20, 0, total=30, viewport=10, scrolloff=2)
        assert off == 8

    def test_preserves_offset_when_comfortably_inside(self) -> None:
        assert compute_block_scroll_offset(12, 1, 8, total=30, viewport=10, scrolloff=2) == 8


class TestBottomPad:
    def test_last_line_expansion_fully_visible(self) -> None:
        # 20 lines, viewport 10, cursor on the last line with 5 rows of
        # rules text: the view scrolls past the end so all 6 rows show.
        off = compute_block_scroll_offset(
            19, 6, 0, total=20, viewport=10, scrolloff=3, bottom_pad=0
        )
        assert 19 - off + 5 <= 9  # block bottom on screen

    def test_bottom_pad_leaves_whitespace_after_last_line(self) -> None:
        off = compute_block_scroll_offset(
            19, 1, 0, total=20, viewport=10, scrolloff=3, bottom_pad=3
        )
        assert off == 20 + 3 - 10  # last line sits 3 rows above the bottom

    def test_pad_never_scrolls_cursor_off_top(self) -> None:
        off = compute_block_scroll_offset(
            0, 1, 0, total=20, viewport=10, scrolloff=3, bottom_pad=3
        )
        assert off == 0

    def test_small_deck_with_tall_expansion_near_bottom(self) -> None:
        # The reported bug: a deck shorter than the viewport, cursor near
        # the bottom, rules text pushed off screen. 20 lines in a 25-row
        # viewport, cursor on row 18 with 8 rows of expansion.
        off = compute_block_scroll_offset(
            18, 9, 0, total=20, viewport=25, scrolloff=3, bottom_pad=3
        )
        assert off > 0
        assert 18 - off + 8 <= 24

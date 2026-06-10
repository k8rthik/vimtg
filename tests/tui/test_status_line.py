"""Tests for StatusLine — mode badge, filename, modified indicator, vcs branch."""

from __future__ import annotations

from vimtg.editor.modes import Mode
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.status_line import MODE_DISPLAY, StatusLine


def _style_for(label: str, plain: str, text) -> str:
    """Return concatenated style names covering the span containing `label`."""
    start = plain.index(label)
    styles: list[str] = []
    for span in text.spans:
        if span.start <= start < span.end:
            styles.append(str(span.style))
    return " ".join(styles)


class TestModeBadge:
    def test_normal_mode_shows_normal_label(self) -> None:
        sl = StatusLine()
        sl.mode = Mode.NORMAL
        text = sl.render()
        assert "-- NORMAL --" in text.plain

    def test_insert_mode_shows_insert_label(self) -> None:
        sl = StatusLine()
        sl.mode = Mode.INSERT
        text = sl.render()
        assert "-- INSERT --" in text.plain

    def test_visual_mode_shows_visual_label(self) -> None:
        sl = StatusLine()
        sl.mode = Mode.VISUAL
        text = sl.render()
        assert "-- VISUAL --" in text.plain

    def test_visual_line_distinct_from_visual(self) -> None:
        sl = StatusLine()
        sl.mode = Mode.VISUAL_LINE
        text = sl.render()
        assert "-- V-LINE --" in text.plain
        assert "-- VISUAL --" not in text.plain

    def test_command_mode_has_no_mode_label(self) -> None:
        """COMMAND/SEARCH mode hide the label since the command line takes over."""
        sl = StatusLine()
        sl.mode = Mode.COMMAND
        text = sl.render()
        assert "-- NORMAL --" not in text.plain
        assert "-- INSERT --" not in text.plain

    def test_each_mode_color_in_display_table(self) -> None:
        """Every Mode value has a display entry — protects against silent additions."""
        for mode in Mode:
            assert mode in MODE_DISPLAY


class TestFilenameAndModified:
    def test_filename_appears(self) -> None:
        sl = StatusLine()
        sl.filename = "burn.deck"
        text = sl.render()
        assert "burn.deck" in text.plain

    def test_modified_indicator_only_when_modified(self) -> None:
        sl = StatusLine()
        sl.filename = "burn.deck"
        sl.modified = False
        assert "[+]" not in sl.render().plain

        sl.modified = True
        assert "[+]" in sl.render().plain

    def test_modified_indicator_uses_red_style(self) -> None:
        sl = StatusLine()
        sl.filename = "burn.deck"
        sl.modified = True
        text = sl.render()
        styles = _style_for("[+]", text.plain, text)
        assert COLORS["mana_red"] in styles


class TestCardCount:
    def test_card_count_displayed(self) -> None:
        sl = StatusLine()
        sl.card_count = 60
        text = sl.render()
        assert "60 cards" in text.plain

    def test_card_count_zero_still_shown(self) -> None:
        sl = StatusLine()
        sl.card_count = 0
        text = sl.render()
        assert "0 cards" in text.plain


class TestCursorPosition:
    def test_cursor_uses_one_based_line_number(self) -> None:
        """vim is 1-indexed for display — cursor_line=0 should render as Ln 1."""
        sl = StatusLine()
        sl.cursor_line = 0
        sl.total_lines = 25
        text = sl.render()
        assert "Ln 1/25" in text.plain

    def test_cursor_at_end(self) -> None:
        sl = StatusLine()
        sl.cursor_line = 24
        sl.total_lines = 25
        text = sl.render()
        assert "Ln 25/25" in text.plain


class TestVcsBranch:
    def test_no_branch_no_brackets(self) -> None:
        sl = StatusLine()
        assert "[" not in sl.render().plain or "[+]" in sl.render().plain

    def test_branch_appears_in_brackets(self) -> None:
        sl = StatusLine()
        sl.vcs_branch = "main"
        text = sl.render()
        assert "[main]" in text.plain

    def test_branch_snapshot_count(self) -> None:
        sl = StatusLine()
        sl.vcs_branch = "feature"
        sl.vcs_snapshot_count = 7
        text = sl.render()
        assert "[feature]" in text.plain
        assert "(7)" in text.plain

    def test_branch_no_snapshot_count_when_zero(self) -> None:
        """A zero snapshot count is noise — should be suppressed."""
        sl = StatusLine()
        sl.vcs_branch = "main"
        sl.vcs_snapshot_count = 0
        text = sl.render()
        assert "(0)" not in text.plain


class TestSegmentOrdering:
    def test_segments_appear_in_canonical_order(self) -> None:
        """mode | filename | modified | cards | branch | line-pos."""
        sl = StatusLine()
        sl.mode = Mode.NORMAL
        sl.filename = "burn.deck"
        sl.modified = True
        sl.card_count = 60
        sl.vcs_branch = "main"
        sl.vcs_snapshot_count = 3
        sl.cursor_line = 5
        sl.total_lines = 60
        plain = sl.render().plain
        order = [
            plain.index("-- NORMAL --"),
            plain.index("burn.deck"),
            plain.index("[+]"),
            plain.index("60 cards"),
            plain.index("[main]"),
            plain.index("Ln 6/60"),
        ]
        assert order == sorted(order), f"segments out of order: {order}"

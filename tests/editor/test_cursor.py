"""Tests for the Cursor dataclass."""

from __future__ import annotations

import pytest

from vimtg.editor.cursor import Cursor


class TestCursor:
    def test_frozen(self) -> None:
        c = Cursor(row=0, col=0)
        with pytest.raises(AttributeError):
            c.row = 5  # type: ignore[misc]

    def test_defaults(self) -> None:
        c = Cursor()
        assert c.row == 0
        assert c.col == 0

    def test_clamp_within_bounds(self) -> None:
        c = Cursor(row=3, col=5)
        clamped = c.clamp(max_row=10, max_col=20)
        assert clamped.row == 3
        assert clamped.col == 5

    def test_clamp_exceeds_max(self) -> None:
        c = Cursor(row=100, col=50)
        clamped = c.clamp(max_row=10, max_col=20)
        assert clamped.row == 10
        assert clamped.col == 20

    def test_clamp_negative(self) -> None:
        c = Cursor(row=-5, col=-3)
        clamped = c.clamp(max_row=10, max_col=10)
        assert clamped.row == 0
        assert clamped.col == 0

    def test_move_to(self) -> None:
        c = Cursor(row=0, col=0)
        moved = c.move_to(row=5, col=3)
        assert moved.row == 5
        assert moved.col == 3
        # Original unchanged
        assert c.row == 0
        assert c.col == 0

    def test_move_to_default_col(self) -> None:
        c = Cursor(row=0, col=5)
        moved = c.move_to(row=3)
        assert moved.row == 3
        assert moved.col == 0

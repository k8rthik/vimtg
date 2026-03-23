"""Immutable cursor position for the deck editor.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cursor:
    row: int = 0
    col: int = 0

    def clamp(self, max_row: int, max_col: int = 0) -> Cursor:
        """Return a new Cursor clamped within [0, max_row] x [0, max_col]."""
        return Cursor(
            row=max(0, min(self.row, max_row)),
            col=max(0, min(self.col, max_col)),
        )

    def move_to(self, row: int, col: int = 0) -> Cursor:
        """Return a new Cursor at the given position."""
        return Cursor(row=row, col=col)

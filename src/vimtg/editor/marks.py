"""Immutable vim-style mark storage for bookmarking cursor positions.

Marks are single-character labels ('a'-'z') mapped to (row, col) positions.
Insert and delete operations shift marks to stay consistent with buffer changes.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mark:
    row: int
    col: int = 0


class MarkStore:
    """Immutable-style mark storage. All mutations return new instances."""

    __slots__ = ("_marks",)

    def __init__(self) -> None:
        self._marks: dict[str, Mark] = {}

    def set(self, name: str, row: int, col: int = 0) -> MarkStore:
        """Return new MarkStore with mark set."""
        new = MarkStore()
        new._marks = {**self._marks, name: Mark(row=row, col=col)}
        return new

    def get(self, name: str) -> Mark | None:
        """Return mark by name, or None if unset."""
        return self._marks.get(name)

    def update_for_insert(self, line: int, count: int) -> MarkStore:
        """Shift marks at or below insertion point down by count lines."""
        new = MarkStore()
        new._marks = {}
        for name, mark in self._marks.items():
            if mark.row >= line:
                new._marks[name] = Mark(row=mark.row + count, col=mark.col)
            else:
                new._marks[name] = mark
        return new

    def update_for_delete(self, start: int, end: int) -> MarkStore:
        """Clear marks in deleted range, shift marks below range up."""
        new = MarkStore()
        new._marks = {}
        deleted_count = end - start + 1
        for name, mark in self._marks.items():
            if start <= mark.row <= end:
                continue  # mark was in deleted range — remove it
            if mark.row > end:
                new._marks[name] = Mark(row=mark.row - deleted_count, col=mark.col)
            else:
                new._marks[name] = mark
        return new

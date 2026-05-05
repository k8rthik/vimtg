"""Filtered view of a Buffer with tag-based visibility.

Read-only wrapper — does not modify the underlying buffer.
TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from vimtg.domain.tags import TagFilter, matches_filter
from vimtg.editor.buffer import Buffer


class FilteredView:
    """Read-only view of a Buffer with tag filtering applied.

    Non-card lines (comments, headers, blanks) are always visible.
    Card lines are visible only if their tags satisfy the filter.
    """

    __slots__ = ("_buffer", "_filter", "_visible")

    def __init__(self, buffer: Buffer, tag_filter: TagFilter | None = None) -> None:
        self._buffer = buffer
        self._filter = tag_filter
        self._visible: frozenset[int] | None = None

    def _compute_visible(self) -> frozenset[int]:
        if self._visible is not None:
            return self._visible
        if self._filter is None:
            self._visible = frozenset(range(self._buffer.line_count()))
            return self._visible

        visible: set[int] = set()
        for i in range(self._buffer.line_count()):
            if not self._buffer.is_card_line(i):
                visible.add(i)
            else:
                tags = self._buffer.tags_at(i)
                if matches_filter(tags, self._filter):
                    visible.add(i)
        self._visible = frozenset(visible)
        return self._visible

    def is_visible(self, line: int) -> bool:
        """Check if a line is visible under the current filter."""
        if self._filter is None:
            return True
        return line in self._compute_visible()

    def next_visible(self, from_line: int) -> int | None:
        """Find the next visible line after from_line, or None."""
        visible = self._compute_visible()
        for i in range(from_line + 1, self._buffer.line_count()):
            if i in visible:
                return i
        return None

    def prev_visible(self, from_line: int) -> int | None:
        """Find the previous visible line before from_line, or None."""
        visible = self._compute_visible()
        for i in range(from_line - 1, -1, -1):
            if i in visible:
                return i
        return None

    def visible_count(self) -> int:
        """Count visible lines."""
        return len(self._compute_visible())

    def hidden_card_count(self) -> int:
        """Count hidden card lines."""
        if self._filter is None:
            return 0
        total_cards = sum(
            1 for i in range(self._buffer.line_count())
            if self._buffer.is_card_line(i)
        )
        visible_cards = sum(
            1 for i in range(self._buffer.line_count())
            if self._buffer.is_card_line(i) and self.is_visible(i)
        )
        return total_cards - visible_cards

    def hidden_ranges(self) -> list[tuple[int, int, int]]:
        """Return contiguous hidden card ranges as (start, end, count) tuples."""
        if self._filter is None:
            return []
        ranges: list[tuple[int, int, int]] = []
        run_start: int | None = None
        run_count = 0
        for i in range(self._buffer.line_count()):
            if self._buffer.is_card_line(i) and not self.is_visible(i):
                if run_start is None:
                    run_start = i
                run_count += 1
            else:
                if run_start is not None:
                    ranges.append((run_start, i - 1, run_count))
                    run_start = None
                    run_count = 0
        if run_start is not None:
            ranges.append((run_start, self._buffer.line_count() - 1, run_count))
        return ranges

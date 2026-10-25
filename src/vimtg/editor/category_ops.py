"""Range-based category mutations shared by :category and the gc/gC keys,
so the ex-command and key-input paths never carry separate copies of
these loops.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from vimtg.domain.categories import CategoryFilter, matches_category
from vimtg.editor.buffer import Buffer


def set_category_in_range(
    buf: Buffer, start: int, end: int, name: str
) -> tuple[Buffer, int]:
    """Set the category on every card line in range. Returns (buffer, count)."""
    count = 0
    for line in range(start, end + 1):
        if buf.is_card_line(line):
            buf = buf.set_category(line, name)
            count += 1
    return buf, count


def clear_category_in_range(
    buf: Buffer, start: int, end: int
) -> tuple[Buffer, int]:
    """Clear the category from card lines in range. Returns (buffer, cleared)."""
    count = 0
    for line in range(start, end + 1):
        if buf.is_card_line(line) and buf.category_at(line):
            buf = buf.set_category(line, "")
            count += 1
    return buf, count


def filter_hides(buf: Buffer, line: int, filt: CategoryFilter | None) -> bool:
    """Whether the view filter dims `line`: a card line whose category
    fails the expression. Headers and comments are never hidden."""
    return (
        filt is not None
        and buf.is_card_line(line)
        and not matches_category(buf.category_at(line), filt)
    )


def count_filter_matches(buf: Buffer, filt: CategoryFilter) -> tuple[int, int]:
    """(matching, total) card-line counts for a filter."""
    rows = [i for i in range(buf.line_count()) if buf.is_card_line(i)]
    hidden = sum(filter_hides(buf, i, filt) for i in rows)
    return len(rows) - hidden, len(rows)


def filter_status_message(visible: int, total: int) -> str:
    """One wording for the Space f / :filter status message."""
    return f"Filter: {visible}/{total} cards match (:filter! clears)"

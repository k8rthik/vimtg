"""Range-based category mutations shared by :category and the gc/gC keys.

Mirrors tag_ops so the ex-command and key-input paths never carry
separate copies of these loops.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

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

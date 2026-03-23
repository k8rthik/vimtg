"""Pure-function vim-style motions for navigating a deck buffer.

Each motion: (cursor, buffer, count) -> Cursor
TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from collections.abc import Callable

from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.cursor import Cursor


def motion_down(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    """Move down, skipping blank lines."""
    pos = cursor.row
    moved = 0
    while moved < count and pos < buffer.line_count() - 1:
        pos += 1
        if buffer.get_line(pos).line_type != LineType.BLANK:
            moved += 1
    return cursor.move_to(pos, cursor.col)


def motion_up(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    """Move up, skipping blank lines."""
    pos = cursor.row
    moved = 0
    while moved < count and pos > 0:
        pos -= 1
        if buffer.get_line(pos).line_type != LineType.BLANK:
            moved += 1
    return cursor.move_to(pos, cursor.col)


def motion_line_start(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    return cursor.move_to(cursor.row, 0)


def motion_line_end(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    return cursor.move_to(cursor.row, len(buffer.get_line(cursor.row).text))


def motion_first_line(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    return cursor.move_to(0, 0)


def motion_last_line(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    return cursor.move_to(buffer.line_count() - 1, 0)


def motion_goto_line(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    """Go to line number (1-indexed count)."""
    target = min(count - 1, buffer.line_count() - 1)
    return cursor.move_to(max(0, target), 0)


def motion_next_card(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    """Jump forward to the next card line, repeated count times."""
    pos = cursor.row
    for _ in range(count):
        nxt = buffer.next_card_line(pos)
        if nxt is None:
            break
        pos = nxt
    return cursor.move_to(pos, 0)


def motion_prev_card(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    """Jump backward to the previous card line, repeated count times."""
    pos = cursor.row
    for _ in range(count):
        prev = buffer.prev_card_line(pos)
        if prev is None:
            break
        pos = prev
    return cursor.move_to(pos, 0)


def motion_next_section(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    """Jump to the first card of the next section (past blank/comment gap)."""
    pos = cursor.row
    for _ in range(count):
        # Skip current section's card lines
        while pos < buffer.line_count() - 1 and buffer.is_card_line(pos):
            pos += 1
        # Skip gap (blank/comment lines)
        while pos < buffer.line_count() - 1 and not buffer.is_card_line(pos):
            pos += 1
    return cursor.move_to(pos, 0)


def motion_prev_section(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    """Jump to the first card of the previous section."""
    pos = cursor.row
    for _ in range(count):
        # Skip backwards past current section
        while pos > 0 and buffer.is_card_line(pos - 1):
            pos -= 1
        # Skip backwards past gap
        while pos > 0 and not buffer.is_card_line(pos - 1):
            pos -= 1
        # Skip backwards to start of previous section
        while pos > 0 and buffer.is_card_line(pos - 1):
            pos -= 1
    return cursor.move_to(pos, 0)


def motion_section_header_next(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    """]] — Jump forward to the next section header comment."""
    pos = cursor.row
    for _ in range(count):
        pos += 1
        while pos < buffer.line_count():
            if buffer.get_line(pos).line_type == LineType.SECTION_HEADER:
                break
            pos += 1
        if pos >= buffer.line_count():
            pos = buffer.line_count() - 1
            break
    return cursor.move_to(pos, 0)


def motion_section_header_prev(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    """[[ — Jump backward to the previous section header comment."""
    pos = cursor.row
    for _ in range(count):
        pos -= 1
        while pos >= 0:
            if buffer.get_line(pos).line_type == LineType.SECTION_HEADER:
                break
            pos -= 1
        if pos < 0:
            pos = 0
            break
    return cursor.move_to(pos, 0)


def motion_half_page_down(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    new_row = min(cursor.row + 15 * count, buffer.line_count() - 1)
    return cursor.move_to(new_row, cursor.col)


def motion_half_page_up(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    new_row = max(cursor.row - 15 * count, 0)
    return cursor.move_to(new_row, cursor.col)


MotionFn = Callable[[Cursor, Buffer, int], Cursor]

MOTION_REGISTRY: dict[str, MotionFn] = {
    "j": motion_down,
    "k": motion_up,
    "h": motion_line_start,
    "l": motion_line_end,
    "0": motion_line_start,
    "$": motion_line_end,
    "gg": motion_first_line,
    "G": motion_last_line,
    "w": motion_next_card,
    "b": motion_prev_card,
    "{": motion_prev_section,
    "}": motion_next_section,
    "left_curly_bracket": motion_prev_section,
    "right_curly_bracket": motion_next_section,
    "[[": motion_section_header_prev,
    "]]": motion_section_header_next,
    "ctrl_d": motion_half_page_down,
    "ctrl_u": motion_half_page_up,
}

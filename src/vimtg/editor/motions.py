"""Pure-function vim-style motions for navigating a deck buffer.

Each motion: (cursor, buffer, count) -> Cursor
TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from collections.abc import Callable

from vimtg.domain.deck_lines import parse_zone_header
from vimtg.editor.buffer import HEADER_LINE_TYPES, Buffer, LineType
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


def is_section_header(buffer: Buffer, row: int) -> bool:
    """A section or sideboard-plan header: where ]] and [[ stop. DCK:
    and SB: open zone blocks, not sections (docs/deck-format.md)."""
    line = buffer.get_line(row)
    return line.line_type in HEADER_LINE_TYPES and parse_zone_header(line.text) is None


def motion_section_header_next(cursor: Cursor, buffer: Buffer, count: int = 1) -> Cursor:
    """]] — Jump forward to the next section header comment."""
    pos = cursor.row
    for _ in range(count):
        pos += 1
        while pos < buffer.line_count():
            if is_section_header(buffer, pos):
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
            if is_section_header(buffer, pos):
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


def _nearest_non_blank(buffer: Buffer, row: int, top: int, bottom: int, step: int) -> int:
    """`row` if it is not blank, else the first non-blank row stepping
    by `step` (then the other way) within [top, bottom]; `row` when the
    whole band is blank."""
    for direction in (step, -step):
        pos = row
        while top <= pos <= bottom:
            if buffer.get_line(pos).line_type != LineType.BLANK:
                return pos
            pos += direction
    return row


def _clamp_band(buffer: Buffer, band: tuple[int, int]) -> tuple[int, int]:
    last = max(0, buffer.line_count() - 1)
    top = max(0, min(band[0], last))
    return top, max(top, min(band[1], last))


def motion_view_top(
    cursor: Cursor, buffer: Buffer, band: tuple[int, int], count: int = 1,
) -> Cursor:
    """H — the count-th line from the top of the visible band."""
    top, bottom = _clamp_band(buffer, band)
    row = min(top + count - 1, bottom)
    return cursor.move_to(_nearest_non_blank(buffer, row, top, bottom, 1), 0)


def motion_view_middle(
    cursor: Cursor, buffer: Buffer, band: tuple[int, int], count: int = 1,
) -> Cursor:
    """M — the middle line of the visible band."""
    top, bottom = _clamp_band(buffer, band)
    row = (top + bottom) // 2
    return cursor.move_to(_nearest_non_blank(buffer, row, top, bottom, 1), 0)


def motion_view_bottom(
    cursor: Cursor, buffer: Buffer, band: tuple[int, int], count: int = 1,
) -> Cursor:
    """L — the count-th line from the bottom of the visible band."""
    top, bottom = _clamp_band(buffer, band)
    row = max(bottom - (count - 1), top)
    return cursor.move_to(_nearest_non_blank(buffer, row, top, bottom, -1), 0)


MotionFn = Callable[[Cursor, Buffer, int], Cursor]
# View motions also take the (top, bottom) rows the deck view shows
ViewMotionFn = Callable[[Cursor, Buffer, tuple[int, int], int], Cursor]

MOTION_REGISTRY: dict[str, MotionFn] = {
    "j": motion_down,
    "k": motion_up,
    # gg takes a count like G does: 5gg is line 5, bare gg line 1
    "gg": motion_goto_line,
    "G": motion_last_line,
    "w": motion_next_card,
    "b": motion_prev_card,
    "{": motion_prev_section,
    "}": motion_next_section,
    "[[": motion_section_header_prev,
    "]]": motion_section_header_next,
    "ctrl_d": motion_half_page_down,
    "ctrl_u": motion_half_page_up,
}

# H / M / L depend on the viewport, so they are not operator targets
VIEW_MOTIONS: dict[str, ViewMotionFn] = {
    "H": motion_view_top,
    "M": motion_view_middle,
    "L": motion_view_bottom,
}

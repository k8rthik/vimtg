"""Vim-style text objects adapted for deck editing.

Maps iw/aw to inner/around card (line-wise) and ip/ap to
inner/around section (contiguous card blocks).

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from collections.abc import Callable

from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.cursor import Cursor


def text_object_inner_card(
    cursor: Cursor, buffer: Buffer
) -> tuple[int, int] | None:
    """iw -- inner card: the current card line (line-wise for deck context)."""
    if buffer.is_card_line(cursor.row):
        return (cursor.row, cursor.row)
    return None


def text_object_around_card(
    cursor: Cursor, buffer: Buffer
) -> tuple[int, int] | None:
    """aw -- around card: same as iw for line-wise deck ops."""
    return text_object_inner_card(cursor, buffer)


def text_object_inner_section(
    cursor: Cursor, buffer: Buffer
) -> tuple[int, int] | None:
    """ip -- inner section: card lines in current section.

    Returns the range of contiguous card lines surrounding the cursor.
    Does NOT include section headers or blank lines.
    If cursor is on a non-card line, searches downward for the nearest section.
    """
    rng = buffer.section_range(cursor.row)
    if rng is not None:
        return rng
    # Cursor is on a comment/blank -- try looking down for nearest section
    for i in range(cursor.row, buffer.line_count()):
        if buffer.is_card_line(i):
            return buffer.section_range(i)
    return None


def text_object_around_section(
    cursor: Cursor, buffer: Buffer
) -> tuple[int, int] | None:
    """ap -- around section: card lines PLUS header above and trailing blank.

    Includes the // comment/section header above the card block and one
    trailing blank line below (if present).
    """
    inner = text_object_inner_section(cursor, buffer)
    if inner is None:
        return None
    start, end = inner
    # Extend start upward to include section header / comment lines (not blanks)
    while start > 0:
        above = buffer.get_line(start - 1)
        if above.line_type in (LineType.SECTION_HEADER, LineType.COMMENT):
            start -= 1
        else:
            break
    # Extend end downward to include one trailing blank
    if end < buffer.line_count() - 1:
        below = buffer.get_line(end + 1)
        if below.line_type == LineType.BLANK:
            end += 1
    return (start, end)


TEXT_OBJECT_REGISTRY: dict[str, Callable[[Cursor, Buffer], tuple[int, int] | None]] = {
    "iw": text_object_inner_card,
    "aw": text_object_around_card,
    "ip": text_object_inner_section,
    "ap": text_object_around_section,
}

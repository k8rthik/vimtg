"""Search commands: :find, :search — TUI-agnostic, zero Textual imports.

Jump to the next card line matching a regex pattern in the buffer.
`n` / `N` repeat the last pattern through find_card_row.
"""

from __future__ import annotations

import re

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor


def find_card_row(
    buffer: Buffer, row: int, pattern: str, *, backward: bool = False,
) -> int | None:
    """The next card line after `row` (before it when `backward`) whose
    text matches `pattern`, wrapping around the buffer; None when no
    other card line matches. Raises re.error on an invalid pattern."""
    regex = re.compile(pattern, re.IGNORECASE)
    total = buffer.line_count()
    step = -1 if backward else 1
    for offset in range(1, total):
        idx = (row + step * offset) % total
        if buffer.is_card_line(idx) and regex.search(buffer.get_line(idx).text):
            return idx
    return None


def cmd_find(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:find pattern — Jump to next card matching pattern in buffer."""
    if not cmd.args:
        ctx.fail("Usage: :find pattern")
        return buffer, cursor

    try:
        idx = find_card_row(buffer, cursor.row, cmd.args)
    except re.error:
        ctx.fail(f"Invalid pattern: {cmd.args}")
        return buffer, cursor

    if idx is not None:
        ctx.message = f"/{cmd.args}"
        return buffer, cursor.move_to(idx, 0)

    ctx.message = f"Pattern not found: {cmd.args}"
    return buffer, cursor


def cmd_search(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:search [query] — Open the card search overlay (as `o` does),
    pre-filled with `query`."""
    ctx.search_open = (cmd.args or "").strip()
    return buffer, cursor


def register_search_commands(registry: CommandRegistry) -> None:
    """Register :find/:f and :search."""
    registry.register("find", cmd_find, aliases=["f"])
    registry.register("search", cmd_search)

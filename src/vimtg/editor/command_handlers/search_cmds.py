"""Search commands: :find — TUI-agnostic, zero Textual imports.

Jump to the next card line matching a regex pattern in the buffer.
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


def cmd_find(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:find pattern — Jump to next card matching pattern in buffer."""
    if not cmd.args:
        ctx.message = "E: Usage: :find pattern"
        ctx.error = True
        return buffer, cursor

    try:
        regex = re.compile(cmd.args, re.IGNORECASE)
    except re.error:
        ctx.message = f"E: Invalid pattern: {cmd.args}"
        ctx.error = True
        return buffer, cursor

    # Search forward from cursor+1, wrapping around
    for offset in range(1, buffer.line_count()):
        idx = (cursor.row + offset) % buffer.line_count()
        if buffer.is_card_line(idx) and regex.search(buffer.get_line(idx).text):
            ctx.message = f"/{cmd.args}"
            return buffer, cursor.move_to(idx, 0)

    ctx.message = f"Pattern not found: {cmd.args}"
    return buffer, cursor


def register_search_commands(registry: CommandRegistry) -> None:
    """Register :find and :f commands."""
    registry.register("find", cmd_find, aliases=["f"])

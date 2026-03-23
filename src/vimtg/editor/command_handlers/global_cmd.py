"""Global command: :g/pattern/cmd, :v/pattern/cmd — TUI-agnostic, zero Textual imports.

Executes a sub-command on lines matching (or not matching) a regex pattern.
Only card/sideboard lines are considered for matching.
"""

from __future__ import annotations

import re

from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor

_MATCHABLE_TYPES = frozenset({
    LineType.CARD_ENTRY,
    LineType.SIDEBOARD_ENTRY,
})


def _parse_global_args(
    args: str,
) -> tuple[str, str] | None:
    """Parse /pattern/command from args string.

    Returns (pattern, sub_cmd) or None on failure.
    The first character of args is the delimiter.
    """
    if not args or len(args) < 3:
        return None

    delim = args[0]
    parts = args[1:].split(delim, 1)
    if len(parts) < 2 or not parts[1].strip():
        return None

    return parts[0], parts[1].strip()


def cmd_global(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:g/pattern/cmd — Execute cmd on lines matching pattern.

    :v/pattern/cmd — Execute on lines NOT matching pattern.

    Supported sub-commands:
    - d: delete the line
    """
    is_inverse = cmd.name == "v"
    parsed = _parse_global_args(cmd.args)

    if parsed is None:
        ctx.message = "E: Usage: :g/pattern/cmd"
        ctx.error = True
        return buffer, cursor

    pattern, sub_cmd = parsed

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        ctx.message = f"E: Invalid pattern: {pattern}"
        ctx.error = True
        return buffer, cursor

    # Find matching lines (only card/sideboard lines)
    matching: list[int] = []
    for i in range(buffer.line_count()):
        line = buffer.get_line(i)
        if line.line_type in _MATCHABLE_TYPES:
            matches = bool(regex.search(line.text))
            if matches != is_inverse:
                matching.append(i)

    if not matching:
        ctx.message = f"Pattern not found: {pattern}"
        return buffer, cursor

    # Execute sub-command
    if sub_cmd == "d":
        new_buffer = buffer
        for line_num in reversed(matching):
            new_buffer, _ = new_buffer.delete_lines(line_num, line_num)
        ctx.message = f"{len(matching)} lines deleted"
        ctx.modified = True
        new_row = min(cursor.row, new_buffer.line_count() - 1)
        return new_buffer, cursor.move_to(max(0, new_row), 0)

    ctx.message = f"E: Unsupported sub-command: {sub_cmd}"
    ctx.error = True
    return buffer, cursor


def register_global_commands(registry: CommandRegistry) -> None:
    """Register :g and :v global commands."""
    registry.register("g", cmd_global)
    registry.register("v", cmd_global)

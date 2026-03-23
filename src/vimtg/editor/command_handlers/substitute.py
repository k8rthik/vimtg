"""Substitute command: :s/old/new/[flags] — TUI-agnostic, zero Textual imports.

Supports per-line, range, and whole-file substitution with optional flags.
Also provides a placeholder :filter command for future view filtering.
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


def _parse_substitute_args(
    args: str,
) -> tuple[str, str, str] | None:
    """Parse /old/new/flags from args string.

    Returns (pattern, replacement, flags) or None on failure.
    The first character of args is the delimiter.
    """
    if not args:
        return None

    delim = args[0]
    parts = args[1:].split(delim)
    if len(parts) < 2:
        return None

    pattern = parts[0]
    replacement = parts[1]
    flags = parts[2] if len(parts) > 2 else ""
    return pattern, replacement, flags


def _resolve_line_range(
    cmd: ParsedCommand, cursor_row: int, line_count: int
) -> tuple[int, int]:
    """Determine the start and end line indices for substitution."""
    if cmd.cmd_range and cmd.cmd_range.is_whole_file:
        return 0, line_count - 1

    if cmd.cmd_range and cmd.cmd_range.start is not None:
        start = cmd.cmd_range.start
        end = cmd.cmd_range.end if cmd.cmd_range.end is not None else start
        return start, end

    return cursor_row, cursor_row


def cmd_substitute(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:s/old/new/[flags] — Substitute text in lines.

    Flags: g (all occurrences per line), i (case-insensitive).
    Range: current line (default), :%s for whole file, :N,Ms for range.
    """
    parsed = _parse_substitute_args(cmd.args)
    if parsed is None:
        ctx.message = "E: Usage: :s/old/new/[flags]"
        ctx.error = True
        return buffer, cursor

    pattern, replacement, flags = parsed
    flag_global = "g" in flags
    re_flags = re.IGNORECASE if "i" in flags else 0

    try:
        regex = re.compile(re.escape(pattern), re_flags)
    except re.error:
        ctx.message = f"E: Invalid pattern: {pattern}"
        ctx.error = True
        return buffer, cursor

    start, end = _resolve_line_range(cmd, cursor.row, buffer.line_count())
    start = max(0, start)
    end = min(end, buffer.line_count() - 1)

    count = 0
    new_buffer = buffer
    for i in range(start, end + 1):
        line = new_buffer.get_line(i)
        max_count = 0 if flag_global else 1
        new_text, n = regex.subn(replacement, line.text, count=max_count)
        if n > 0:
            new_buffer = new_buffer.set_line(i, new_text)
            count += n

    if count > 0:
        ctx.modified = True
        suffix = "s" if count != 1 else ""
        ctx.message = f"{count} substitution{suffix}"
    else:
        ctx.message = f"Pattern not found: {pattern}"

    return new_buffer, cursor


def cmd_filter_view(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:filter pattern — Placeholder for view filtering."""
    ctx.message = f"Filter: {cmd.args} (view filter not yet implemented)"
    return buffer, cursor


def register_substitute_commands(registry: CommandRegistry) -> None:
    """Register :s, :substitute, and :filter commands."""
    registry.register("s", cmd_substitute, aliases=["substitute"])
    registry.register("filter", cmd_filter_view)

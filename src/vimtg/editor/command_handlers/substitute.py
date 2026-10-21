"""Substitute command: :s/old/new/[flags] — TUI-agnostic, zero Textual imports.

Supports per-line, range, and whole-file substitution with optional flags.
The pattern is a regular expression matched case-insensitively, exactly
like / and :g, so whatever / finds :s can change. The replacement uses
vim's syntax: & (or \\0) is the whole match, \\1-\\9 are groups, \\& is a
literal &. An empty pattern reuses the last search (or :g) pattern.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
    command_line_range,
)
from vimtg.editor.cursor import Cursor


def split_delimited(args: str, parts: int) -> list[str] | None:
    """Split '/a/b/c' on its first character into at most `parts`
    fields. A backslash-escaped delimiter is part of the field (with the
    backslash dropped); other escapes are kept for the regex. None when
    there is no delimiter or the first field is unterminated."""
    if not args:
        return None
    delim = args[0]
    fields: list[str] = []
    current: list[str] = []
    i = 1
    while i < len(args):
        ch = args[i]
        if ch == "\\" and i + 1 < len(args):
            nxt = args[i + 1]
            current.append(nxt if nxt == delim else ch + nxt)
            i += 2
            continue
        if ch == delim and len(fields) < parts - 1:
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    fields.append("".join(current))
    if len(fields) < 2 and parts > 1:
        return None
    return fields


def _parse_substitute_args(
    args: str,
) -> tuple[str, str, str] | None:
    """Parse /old/new/flags from args string.

    Returns (pattern, replacement, flags) or None on failure.
    The first character of args is the delimiter.
    """
    fields = split_delimited(args, 3)
    if fields is None:
        return None
    pattern = fields[0]
    replacement = fields[1]
    flags = fields[2] if len(fields) > 2 else ""
    return pattern, replacement, flags


def vim_replacement(replacement: str) -> Callable[[re.Match[str]], str]:
    """A re.sub callable expanding vim's & \\0-\\9 and \\& / \\\\ escapes."""

    def expand(match: re.Match[str]) -> str:
        out: list[str] = []
        i = 0
        while i < len(replacement):
            ch = replacement[i]
            if ch == "&":
                out.append(match.group(0))
            elif ch == "\\" and i + 1 < len(replacement):
                nxt = replacement[i + 1]
                i += 1
                if nxt.isdigit():
                    group = int(nxt)
                    if group <= (match.re.groups or 0):
                        out.append(match.group(group) or "")
                else:
                    out.append(nxt)  # \& \\ and any other escaped char
            else:
                out.append(ch)
            i += 1
        return "".join(out)

    return expand


def compile_search_pattern(pattern: str, *, ignore_case: bool = True) -> re.Pattern[str]:
    """Compile a /, :g, or :s pattern the same way everywhere."""
    return re.compile(pattern, re.IGNORECASE if ignore_case else 0)


def substitute_lines(
    buffer: Buffer,
    rows: list[int] | range,
    regex: re.Pattern[str],
    replacement: str,
    *,
    every: bool,
) -> tuple[Buffer, int]:
    """Apply the substitute on `rows`; returns (buffer, substitutions)."""
    expand = vim_replacement(replacement)
    count = 0
    for i in rows:
        line = buffer.get_line(i)
        new_text, n = regex.subn(expand, line.text, count=0 if every else 1)
        if n > 0 and new_text != line.text:
            buffer = buffer.set_line(i, new_text)
        count += n
    return buffer, count


def _resolve_line_range(
    cmd: ParsedCommand, cursor_row: int, line_count: int
) -> tuple[int, int]:
    """Determine the line range for substitution (default: current line)."""
    return command_line_range(cmd, line_count, (cursor_row, cursor_row))


def cmd_substitute(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:s/old/new/[flags] — Substitute text in lines.

    Flags: g (all occurrences per line), I (match case; the default
    ignores case, like / and :g), i (ignore case — the default).
    Range: current line (default), :%s for whole file, :N,Ms for range.
    """
    parsed = _parse_substitute_args(cmd.args)
    if parsed is None:
        ctx.fail("Usage: :s/old/new/[flags]")
        return buffer, cursor

    pattern, replacement, flags = parsed
    if not pattern:
        pattern = ctx.last_pattern
        if not pattern:
            ctx.fail("E35: No previous regular expression")
            return buffer, cursor
    flag_global = "g" in flags

    try:
        regex = compile_search_pattern(pattern, ignore_case="I" not in flags)
    except re.error:
        ctx.fail(f"Invalid pattern: {pattern}")
        return buffer, cursor

    start, end = _resolve_line_range(cmd, cursor.row, buffer.line_count())
    start = max(0, start)
    end = min(end, buffer.line_count() - 1)

    new_buffer, count = substitute_lines(
        buffer, range(start, end + 1), regex, replacement, every=flag_global,
    )

    if count > 0:
        if new_buffer is not buffer:
            ctx.modified = True
        suffix = "s" if count != 1 else ""
        ctx.message = f"{count} substitution{suffix}"
    else:
        ctx.message = f"Pattern not found: {pattern}"

    return new_buffer, cursor


def register_substitute_commands(registry: CommandRegistry) -> None:
    """Register :s and :substitute commands."""
    registry.register("s", cmd_substitute, aliases=["substitute"])

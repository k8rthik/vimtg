"""Global command: :g/pattern/cmd, :v/pattern/cmd — TUI-agnostic, zero Textual imports.

Executes a sub-command on lines matching (or not matching) a regex pattern.
Card lines in every zone are considered for matching — mainboard,
sideboard, maybeboard, command zone, and companion — matched against
the full line text, so `^SB:` or `@ramp` work. Headers, comments,
metadata, and sideboard-plan entries never match. The pattern is
compiled exactly like / and :s (case-insensitive regex); an empty
pattern reuses the last search.
"""

from __future__ import annotations

import re

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.substitute import (
    _parse_substitute_args,
    compile_search_pattern,
    split_delimited,
    substitute_lines,
)
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
    command_line_range,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.operators import store_lines
from vimtg.editor.registers import RegisterStore, is_clipboard_register

SUB_COMMANDS = "d, p, y [x], s/pat/rep/[flags]"


def _parse_global_args(
    args: str,
) -> tuple[str, str] | None:
    """Parse /pattern/command from args string.

    Returns (pattern, sub_cmd) or None on failure.
    The first character of args is the delimiter.
    """
    fields = split_delimited(args, 2)
    if fields is None or not fields[1].strip():
        return None
    return fields[0], fields[1].strip()


def cmd_global(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:g/pattern/cmd — Execute cmd on lines matching pattern.

    :v/pattern/cmd (or :g!) — Execute on lines NOT matching pattern.

    Supported sub-commands:
    - d: delete the lines
    - p: list the matching cards on the command line
    - y [x]: yank the lines (into register x; "A appends)
    - s/pat/rep/[flags]: substitute on each line (an empty pat is the
      :g pattern)
    """
    is_inverse = cmd.name == "v" or cmd.bang
    parsed = _parse_global_args(cmd.args)

    if parsed is None:
        ctx.fail("Usage: :g/pattern/cmd")
        return buffer, cursor

    pattern, sub_cmd = parsed
    if not pattern:
        pattern = ctx.last_pattern
        if not pattern:
            ctx.fail("E35: No previous regular expression")
            return buffer, cursor

    try:
        regex = compile_search_pattern(pattern)
    except re.error:
        ctx.fail(f"Invalid pattern: {pattern}")
        return buffer, cursor

    # Find matching lines (card lines in any zone) — within the
    # command's range (:1,5g/x/d, '<,'>g/x/d); the whole buffer by default
    first, last = command_line_range(cmd, buffer.line_count(), (0, buffer.line_count() - 1))
    matching: list[int] = []
    for i in range(first, last + 1):
        if buffer.is_card_line(i):
            matches = bool(regex.search(buffer.get_line(i).text))
            if matches != is_inverse:
                matching.append(i)

    if not matching:
        ctx.message = f"Pattern not found: {pattern}"
        return buffer, cursor

    name, _, rest = sub_cmd.partition(" ")
    if sub_cmd == "d":
        new_buffer = buffer
        marks = ctx.marks
        for line_num in reversed(matching):
            new_buffer, _ = new_buffer.delete_lines(line_num, line_num)
            if marks is not None:
                marks = marks.update_for_delete(line_num, line_num)
        ctx.marks = marks
        ctx.message = f"{len(matching)} lines deleted"
        ctx.modified = True
        new_row = min(cursor.row, new_buffer.line_count() - 1)
        return new_buffer, cursor.move_to(max(0, new_row), 0)

    if sub_cmd == "p":
        names = [buffer.get_line(i).text.strip() for i in matching]
        ctx.show_listing(
            f"Matches ({len(matching)})", names,
            f"{len(matching)} match(es): " + " | ".join(names),
        )
        return buffer, cursor.move_to(matching[-1], 0)

    if name in ("y", "yank"):
        register = rest.strip() or None
        lines = tuple(buffer.get_line(i).text for i in matching)
        registers = ctx.registers if ctx.registers is not None else RegisterStore()
        ctx.registers = store_lines(registers, register, lines, is_delete=False)
        if is_clipboard_register(register):
            # The TUI performs the copy from ctx.clipboard_text
            ctx.clipboard_text = "\n".join(lines) + "\n"
            ctx.clipboard_label = f"register + ({len(lines)} lines)"
        ctx.message = f"{len(lines)} lines yanked"
        return buffer, cursor

    if sub_cmd.startswith("s") and len(sub_cmd) > 1 and not sub_cmd[1].isalnum():
        sub = _parse_substitute_args(sub_cmd[1:])
        if sub is None:
            ctx.fail("Usage: :g/pattern/s/old/new/[flags]")
            return buffer, cursor
        sub_pattern, replacement, flags = sub
        try:
            sub_regex = (
                compile_search_pattern(sub_pattern, ignore_case="I" not in flags)
                if sub_pattern else regex
            )
        except re.error:
            ctx.fail(f"Invalid pattern: {sub_pattern}")
            return buffer, cursor
        new_buffer, count = substitute_lines(
            buffer, matching, sub_regex, replacement, every="g" in flags,
        )
        if new_buffer is not buffer:
            ctx.modified = True
        ctx.message = f"{count} substitution{'s' if count != 1 else ''}"
        return new_buffer, cursor

    ctx.fail(f"Unsupported sub-command: {sub_cmd} (supported: {SUB_COMMANDS})")
    return buffer, cursor


def register_global_commands(registry: CommandRegistry) -> None:
    """Register :g and :v global commands."""
    registry.register("g", cmd_global, aliases=["global"])
    registry.register("v", cmd_global, aliases=["vglobal"])

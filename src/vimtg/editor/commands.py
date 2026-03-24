"""Ex command parser, registry, and execution — TUI-agnostic, zero Textual imports.

Parses vim-style ex commands like ':5,10sort cmc', ':w', ':q!', ':%sort'.
Commands are registered by name with optional aliases. The registry dispatches
parsed commands to handler functions.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor

_RANGE_PATTERN = re.compile(
    r"^(%|(?:[.\d$]+(?:,[.\d$]+)?))?(.*)$"
)


@dataclass(frozen=True)
class CommandRange:
    """Parsed line range for an ex command. Indices are 0-based."""

    start: int | None = None
    end: int | None = None
    is_whole_file: bool = False

    @staticmethod
    def parse(range_str: str, cursor_row: int, line_count: int) -> CommandRange:
        """Parse range specifiers into a CommandRange.

        Supported formats:
          ''  -> None range (no range specified)
          '%' -> whole file (0 to line_count-1)
          '.' -> current line
          '$' -> last line
          'N' -> single line (1-based input, 0-based output)
          'N,M' -> range (1-based input, 0-based output)
        """
        stripped = range_str.strip()
        if not stripped:
            return CommandRange()

        if stripped == "%":
            return CommandRange(
                start=0, end=max(0, line_count - 1), is_whole_file=True
            )

        last_line = max(0, line_count - 1)

        def _resolve(token: str) -> int:
            if token == ".":
                return cursor_row
            if token == "$":
                return last_line
            return max(0, int(token) - 1)

        if "," in stripped:
            parts = stripped.split(",", maxsplit=1)
            start = _resolve(parts[0].strip())
            end = _resolve(parts[1].strip())
            return CommandRange(start=min(start, end), end=max(start, end))

        single = _resolve(stripped)
        return CommandRange(start=single, end=single)


@dataclass(frozen=True)
class ParsedCommand:
    """Result of parsing an ex command string."""

    name: str
    args: str = ""
    cmd_range: CommandRange | None = None
    bang: bool = False


def parse_command(
    input_str: str, cursor_row: int, line_count: int
) -> ParsedCommand:
    """Parse a raw ex command string into a ParsedCommand.

    Examples:
      ':w'           -> ParsedCommand(name='w', args='')
      ':sort cmc'    -> ParsedCommand(name='sort', args='cmc')
      ':5,10sort'    -> ParsedCommand(name='sort', range=Range(4,9))
      ':%sort'       -> ParsedCommand(name='sort', is_whole_file=True)
      ':q!'          -> ParsedCommand(name='q', bang=True)
      ':.'           -> ParsedCommand(name='', range=current_line)
      ':$'           -> ParsedCommand(name='', range=last_line)
    """
    text = input_str.lstrip(":")

    match = _RANGE_PATTERN.match(text)
    if not match:
        return ParsedCommand(name=text.strip())

    range_part = match.group(1) or ""
    rest = match.group(2).strip()

    cmd_range = (
        CommandRange.parse(range_part, cursor_row, line_count)
        if range_part
        else None
    )

    if not rest:
        return ParsedCommand(name="", cmd_range=cmd_range)

    # Split command name from arguments.
    # Handle both whitespace-separated args (:sort name) and
    # delimiter-attached args (:s/old/new/g, :g/pattern/cmd).
    cmd_match = re.match(r"^([a-zA-Z]+)(!?)(?:\s+(.*)|([^a-zA-Z\s].*))?$", rest)
    if not cmd_match:
        return ParsedCommand(name=rest, cmd_range=cmd_range)

    name = cmd_match.group(1)
    bang = cmd_match.group(2) == "!"
    # group(3) = whitespace-separated args, group(4) = delimiter-attached args
    args = (cmd_match.group(3) or cmd_match.group(4) or "").strip()

    return ParsedCommand(name=name, args=args, cmd_range=cmd_range, bang=bang)


@dataclass
class EditorContext:
    """Mutable context passed to command handlers for side effects."""

    file_path: Path | None = None
    modified: bool = False
    quit_requested: bool = False
    message: str = ""
    error: bool = False
    save_fn: Callable[[Path, str], None] | None = None


CommandHandler = Callable[
    [Buffer, Cursor, ParsedCommand, EditorContext], tuple[Buffer, Cursor]
]


@dataclass
class CommandRegistry:
    """Registry mapping ex command names to handler functions."""

    _commands: dict[str, CommandHandler] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict)

    def register(
        self,
        name: str,
        handler: CommandHandler,
        aliases: list[str] | None = None,
    ) -> None:
        """Register a command handler with optional aliases."""
        self._commands[name] = handler
        for alias in aliases or []:
            self._aliases[alias] = name

    def execute(
        self,
        cmd: ParsedCommand,
        buffer: Buffer,
        cursor: Cursor,
        ctx: EditorContext,
    ) -> tuple[Buffer, Cursor]:
        """Look up and execute a command. Sets ctx.message on unknown command."""
        resolved = self._aliases.get(cmd.name, cmd.name)
        handler = self._commands.get(resolved)
        if handler is None:
            ctx.message = f"Unknown command: {cmd.name}"
            ctx.error = True
            return buffer, cursor
        return handler(buffer, cursor, cmd, ctx)

    def get_completions(self, prefix: str) -> list[str]:
        """Return sorted command names matching prefix."""
        all_names = sorted(set(self._commands) | set(self._aliases))
        return [n for n in all_names if n.startswith(prefix)]

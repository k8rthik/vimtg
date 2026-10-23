"""Ex command parser, registry, and execution — TUI-agnostic, zero Textual imports.

Parses vim-style ex commands like ':5,10sort cmc', ':w', ':q!', ':%sort'.
Commands are registered by name with optional aliases. The registry dispatches
parsed commands to handler functions.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository
    from vimtg.data.file_io import FileStamp
    from vimtg.domain.card import Card
    from vimtg.services.history_service import HistoryService

# One address: a line number, '.', '$', or a mark ('a, '<, '>)
_ADDRESS = r"(?:'[a-zA-Z<>]|[.\d$]+)"
_RANGE_PATTERN = re.compile(
    rf"^(%|(?:{_ADDRESS}(?:,{_ADDRESS})?))?(.*)$"
)


class RangeError(ValueError):
    """An ex range that names no line (vim's E20 for an unset mark)."""


@dataclass(frozen=True)
class CommandRange:
    """Parsed line range for an ex command. Indices are 0-based."""

    start: int | None = None
    end: int | None = None
    is_whole_file: bool = False
    # A line number past the end was given (:999d). A bare :999 still
    # goes to the last line; a command on that range is vim's E16.
    out_of_range: bool = False

    @staticmethod
    def parse(
        range_str: str,
        cursor_row: int,
        line_count: int,
        marks: Mapping[str, int] | None = None,
    ) -> CommandRange:
        """Parse range specifiers into a CommandRange.

        Supported formats:
          ''  -> None range (no range specified)
          '%' -> whole file (0 to line_count-1)
          '.' -> current line
          '$' -> last line
          'N' -> single line (1-based input, 0-based output)
          'N,M' -> range (1-based input, 0-based output)
          "'a" -> the row of mark a ('< / '> are the last visual selection)

        Raises RangeError for a mark that is not set.
        """
        stripped = range_str.strip()
        if not stripped:
            return CommandRange()

        if stripped == "%":
            return CommandRange(
                start=0, end=max(0, line_count - 1), is_whole_file=True
            )

        last_line = max(0, line_count - 1)
        past_end = False

        def _resolve(token: str) -> int:
            nonlocal past_end
            if token == ".":
                return cursor_row
            if token == "$":
                return last_line
            if token.startswith("'"):
                row = (marks or {}).get(token[1:])
                if row is None:
                    raise RangeError("E20: Mark not set")
                return max(0, min(row, last_line))
            try:
                number = int(token)
            except ValueError:
                # Tokens like "1.5" or "$5" pass the range regex but
                # aren't valid line numbers — treat as current line.
                return cursor_row
            if number > max(1, line_count):
                past_end = True
                return last_line
            return max(0, number - 1)

        if "," in stripped:
            parts = stripped.split(",", maxsplit=1)
            start = _resolve(parts[0].strip())
            end = _resolve(parts[1].strip())
            return CommandRange(
                start=min(start, end), end=max(start, end), out_of_range=past_end,
            )

        single = _resolve(stripped)
        return CommandRange(start=single, end=single, out_of_range=past_end)


@dataclass(frozen=True)
class ParsedCommand:
    """Result of parsing an ex command string."""

    name: str
    args: str = ""
    cmd_range: CommandRange | None = None
    bang: bool = False


def parse_command(
    input_str: str,
    cursor_row: int,
    line_count: int,
    marks: Mapping[str, int] | None = None,
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
      ":'<,'>d"      -> ParsedCommand(name='d', range=visual selection)

    `marks` maps mark names to rows for 'a style addresses; an unset
    mark raises RangeError.
    """
    text = input_str.lstrip(":")

    match = _RANGE_PATTERN.match(text)
    if not match:
        return ParsedCommand(name=text.strip())

    range_part = match.group(1) or ""
    rest = match.group(2).strip()

    cmd_range = (
        CommandRange.parse(range_part, cursor_row, line_count, marks)
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


def resolve_command_range(cmd: ParsedCommand) -> tuple[int, int] | None:
    """Return the explicit (start, end) range of a command, or None.

    Normalizes reversed ranges and defaults end to start. Callers pick
    their own fallback when None (current line, current section, ...) —
    previously each handler re-implemented this with different bugs.
    """
    rng = cmd.cmd_range
    if rng is None or rng.start is None:
        return None
    end = rng.end if rng.end is not None else rng.start
    return (min(rng.start, end), max(rng.start, end))


def command_line_range(
    cmd: ParsedCommand, line_count: int, default: tuple[int, int]
) -> tuple[int, int]:
    """The lines an ex command addresses: its explicit range ('%' is
    the whole buffer), else `default` (the cursor line, the current
    section, ...), clamped to the buffer so a stale row never
    indexes past the end. The one place handlers get this from."""
    explicit = resolve_command_range(cmd)
    start, end = explicit if explicit is not None else default
    last = max(0, line_count - 1)
    return max(0, min(start, last)), max(0, min(end, last))


def _goto_range(cmd: ParsedCommand, buffer: Buffer, cursor: Cursor) -> Cursor:
    """:12, :$, :. — a bare range moves to its last line, as in vim."""
    rng = cmd.cmd_range
    assert rng is not None
    row = rng.end if rng.end is not None else rng.start
    if row is None:
        return cursor
    return cursor.move_to(max(0, min(row, buffer.line_count() - 1)), 0)


@dataclass
class EditorContext:
    """Mutable context passed to command handlers for side effects."""

    file_path: Path | None = None
    file_saved: bool = False  # set by :w — gates auto-snapshot
    # file_path's (mtime, size) when last read or written; None = unknown
    # (no change check). :w refuses without ! when the disk differs.
    disk_stamp: FileStamp | None = None
    modified: bool = False
    quit_requested: bool = False
    greeter_requested: bool = False
    message: str = ""
    error: bool = False
    save_fn: Callable[[Path, str], None] | None = None
    settings: Any = None
    settings_changed: bool = False
    open_config_screen: bool = False
    open_history_screen: bool = False
    open_help_screen: bool = False
    help_topic: str | None = None
    vcs_commit_description: str = ""
    vcs_checkpoint_name: str = ""
    vcs_list_branches: bool = False
    vcs_create_branch: str = ""
    vcs_switch_branch: str = ""
    vcs_merge_target: str = ""
    vcs_rebase_target: str = ""
    resolved_cards: dict[str, Card] | None = None
    card_repo: CardRepository | None = None
    history: HistoryService | None = None
    # Tag-filter request: tag_filter_set marks that the handler changed
    # the filter (to a TagFilter, or to None to clear it)
    tag_filter: Any = None
    tag_filter_set: bool = False
    remapper: Any = None  # KeyRemapper — :map/:unmap mutate it
    # A split pane is open beside the editor: :q / :wq / :x close it
    # (the window) instead of quitting
    pane_open: bool = False
    # Companion-pane requests (SplitOpen / EdhrecOpen from editor.splits)
    split_open: Any = None
    split_close: bool = False
    edhrec_open: Any = None
    analytics_open: Any = None
    hand_open: Any = None  # HandOpen — sample-hand overlay request
    import_url: str = ""  # deck-site URL to fetch asynchronously
    # System-clipboard copy request: the TUI owns the terminal, so it
    # performs the copy and words the result (clipboard_label names it)
    clipboard_text: str | None = None
    clipboard_label: str = ""
    card_sync: str = ""  # :sync request — "sync", or "force" for :sync!
    # Active sideboard plan: seeded from editor state; active_plan_set
    # marks that the handler changed it (to a name, or None to clear)
    active_plan: str | None = None
    active_plan_set: bool = False
    # Editor registers and marks (RegisterStore / MarkStore): seeded from
    # the session; a handler replaces them to change them
    registers: Any = None
    marks: Any = None
    # The last / ? * # pattern — :s// and :g// reuse it
    last_pattern: str = ""
    # :undo / :redo — the session steps its history once ("undo"/"redo")
    undo_request: str = ""
    # :e — the deck to open in place of this one
    edit_path: Path | None = None
    # :q! / :e! / :home! threw unsaved changes away on purpose: the
    # buffer's crash-recovery copy goes with them
    discard_requested: bool = False
    # Keys an unnamed buffer's recovery copy (named decks use the path)
    recovery_id: str | None = None
    # Screen-level view with no buffer change (":messages", ":tips")
    ui_request: str = ""
    # :search — open the card search overlay with this query (None = no)
    search_open: str | None = None

    def fail(self, message: str) -> None:
        """Set an error message with the standard 'E: ' prefix."""
        self.message = message if message.startswith("E: ") else f"E: {message}"
        self.error = True


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
        """Register a command handler with optional aliases.

        Raises ValueError on a duplicate name or alias — silently
        overwriting would let one module shadow another's command.
        """
        if name in self._commands or name in self._aliases:
            raise ValueError(f"Command already registered: {name}")
        self._commands[name] = handler
        for alias in aliases or []:
            if alias in self._commands or alias in self._aliases:
                raise ValueError(f"Command alias already registered: {alias}")
            self._aliases[alias] = name

    def execute(
        self,
        cmd: ParsedCommand,
        buffer: Buffer,
        cursor: Cursor,
        ctx: EditorContext,
    ) -> tuple[Buffer, Cursor]:
        """Look up and execute a command. Sets ctx.message on unknown command."""
        if not cmd.name and cmd.cmd_range is not None:
            return buffer, _goto_range(cmd, buffer, cursor)
        if cmd.cmd_range is not None and cmd.cmd_range.out_of_range:
            ctx.fail("E16: Invalid range")
            return buffer, cursor
        resolved = self._aliases.get(cmd.name, cmd.name)
        handler = self._commands.get(resolved)
        if handler is None:
            ctx.fail(f"Unknown command: {cmd.name}")
            return buffer, cursor
        return handler(buffer, cursor, cmd, ctx)

    def resolve(self, name: str) -> str:
        """The canonical command name for `name` (aliases resolved)."""
        return self._aliases.get(name, name)

    def get_completions(self, prefix: str) -> list[str]:
        """Return sorted command names matching prefix."""
        all_names = sorted(set(self._commands) | set(self._aliases))
        return [n for n in all_names if n.startswith(prefix)]

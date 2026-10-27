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

# One address: a line number, '.', '$', or a mark ('a, '<, '>), then any
# +N / -N offsets ('+' alone is +1); an offset alone counts from '.'
_ADDRESS = r"(?:(?:'[a-zA-Z<>]|[.\d$]+)(?:[+-]\d*)*|(?:[+-]\d*)+)"
_ADDRESS_PARTS = re.compile(r"^('[a-zA-Z<>]|[.\d$]*)((?:[+-]\d*)*)$")
_OFFSET = re.compile(r"([+-])(\d*)")
_RANGE_PATTERN = re.compile(
    rf"^(%|(?:{_ADDRESS}(?:,{_ADDRESS})?))?(.*)$"
)


# An error message that already carries its code: 'E: ...' or vim's 'E37: ...'
_ERROR_CODE = re.compile(r"^E\d*: ")


def is_error_message(text: str) -> bool:
    """True for an error message: 'E: ...' or a vim-coded 'E37: ...'."""
    return _ERROR_CODE.match(text) is not None


class RangeError(ValueError):
    """An ex range that names no line (vim's E20 for an unset mark)."""


def address_line(
    token: str,
    cursor_row: int,
    line_count: int,
    marks: Mapping[str, int] | None = None,
) -> int | None:
    """The 1-based line an ex address names, offsets applied: '.+1',
    '+3', '$-1', "'a+2". The result may lie outside the buffer (0, or
    past the end) for the caller to judge; None when `token` is not an
    address. A token like '1.5' counts as the cursor line. Raises
    RangeError for a mark that is not set."""
    parts = _ADDRESS_PARTS.match(token.strip())
    if parts is None:
        return None
    base, offsets = parts.groups()
    last_line = max(0, line_count - 1)
    if base in ("", "."):
        line = cursor_row + 1
    elif base == "$":
        line = last_line + 1
    elif base.startswith("'"):
        row = (marks or {}).get(base[1:])
        if row is None:
            raise RangeError("E20: Mark not set")
        line = max(0, min(row, last_line)) + 1
    else:
        line = int(base) if base.isdigit() else cursor_row + 1
    for sign, digits in _OFFSET.findall(offsets):
        step = int(digits) if digits else 1
        line += step if sign == "+" else -step
    return line


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
            line = address_line(token, cursor_row, line_count, marks)
            if line is None:
                return cursor_row
            if line > max(1, line_count) or line < 0:
                past_end = True
                return last_line if line > 0 else 0
            return max(0, line - 1)

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


@dataclass(frozen=True)
class Listing:
    """Output of a listing command (:reg, :marks, :categories, :validate ...),
    one entry per line. Its one-line form is the message; the TUI shows
    that when it fits on the command line, else `lines` in a pager
    titled `title`, as vim's more-prompt does."""

    title: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class NewBuffer:
    """:enew / :import: open an unnamed buffer in place of the deck.
    With no `text` it is empty and the new-deck wizard asks for a name
    and format; an import's `text` opens unsaved, `message` (its
    summary) shown once it is up."""

    text: str | None = None
    message: str = ""


E37 = "E37: No write since last change (add ! to override)"


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
    resolved_cards: dict[str, Card] | None = None
    card_repo: CardRepository | None = None
    history: HistoryService | None = None
    # View-filter request: category_filter_set marks that the handler
    # changed the filter (to a CategoryFilter, or to None to clear it)
    category_filter: Any = None
    category_filter_set: bool = False
    remapper: Any = None  # KeyRemapper — :map/:unmap mutate it
    # The side pane is open beside the editor: :q / :wq / :x close it
    # (the window) instead of quitting
    pane_open: bool = False
    # Side-pane requests (EdhrecOpen from editor.splits)
    split_close: bool = False
    edhrec_open: Any = None
    analytics_open: bool = False
    hand_open: Any = None  # HandOpen — sample-hand overlay request
    import_url: str = ""  # deck-site URL to fetch asynchronously
    # System-clipboard copy request: the TUI owns the terminal, so it
    # performs the copy and words the result (clipboard_label names it)
    clipboard_text: str | None = None
    clipboard_label: str = ""
    # Appended to the copy's message ("; 1 warning (see :messages)")
    clipboard_note: str = ""
    # (is_error, text) lines for :messages only, logged before `message`
    logged: list[tuple[bool, str]] = field(default_factory=list)
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
    # :e — the deck to open in place of this one
    edit_path: Path | None = None
    # :q! / :e! / :home! threw unsaved changes away on purpose: the
    # buffer's crash-recovery copy goes with them
    discard_requested: bool = False
    # Keys an unnamed buffer's recovery copy (named decks use the path)
    recovery_id: str | None = None
    # Screen-level view with no buffer change (":messages", ":tips")
    ui_request: str = ""
    # A listing's lines; `message` holds its one-line form
    listing: Listing | None = None
    # :enew / :import — the unnamed buffer to open in place of this one
    new_buffer: NewBuffer | None = None
    # :import! <url> — the fetched deck may replace unsaved changes
    import_force: bool = False
    # The owned-cards Collection (domain.collection): seeded from the
    # editor state; collection_set marks that :collection replaced it
    # (with a Collection, or None to clear)
    collection: Any = None
    collection_set: bool = False

    def show_listing(
        self, title: str, lines: list[str] | tuple[str, ...], summary: str,
        *, error: bool = False,
    ) -> None:
        """Output `lines` under `title`; `summary` is the one-line form."""
        self.listing = Listing(title, tuple(lines))
        self.message = summary
        self.error = error

    def fail(self, message: str) -> None:
        """Set an error message: a vim-coded one ('E37: ...') as it is,
        any other with the generic 'E: ' prefix."""
        self.message = message if is_error_message(message) else f"E: {message}"
        self.error = True


CommandHandler = Callable[
    [Buffer, Cursor, ParsedCommand, EditorContext], tuple[Buffer, Cursor]
]


@dataclass(frozen=True)
class _Command:
    """A registered command: its handler, and whether it takes an
    argument. One that takes none refuses `:cmd junk` with vim's E488
    before the handler runs, so no handler ignores a stray argument."""

    handler: CommandHandler
    takes_args: bool


@dataclass
class CommandRegistry:
    """Registry mapping ex command names to handler functions."""

    _commands: dict[str, _Command] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict)

    def register(
        self,
        name: str,
        handler: CommandHandler,
        aliases: list[str] | None = None,
        *,
        takes_args: bool = True,
    ) -> None:
        """Register a command handler with optional aliases.

        `takes_args=False` declares a command that takes no argument:
        the registry refuses one with E488 and the handler never runs.

        Raises ValueError on a duplicate name or alias — silently
        overwriting would let one module shadow another's command.
        """
        if name in self._commands or name in self._aliases:
            raise ValueError(f"Command already registered: {name}")
        self._commands[name] = _Command(handler, takes_args)
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
        command = self._commands.get(self.resolve(cmd.name))
        if command is None:
            # vim's wording, with the command as typed (fail would add "E: ")
            typed = cmd.name + ("!" if cmd.bang else "") + (f" {cmd.args}" if cmd.args else "")
            ctx.message = f"E492: Not an editor command: {typed}"
            ctx.error = True
            return buffer, cursor
        if cmd.args and not command.takes_args:
            ctx.fail(f"E488: Trailing characters: {cmd.args}")
            return buffer, cursor
        return command.handler(buffer, cursor, cmd, ctx)

    def subset(self, names: tuple[str, ...]) -> CommandRegistry:
        """A registry of just the commands `names`, with their aliases:
        the same handlers, parsing and messages in a smaller vocabulary
        (the greeter's command line)."""
        part = CommandRegistry()
        for name in names:
            aliases = [a for a, target in self._aliases.items() if target == name]
            command = self._commands[name]
            part.register(name, command.handler, aliases, takes_args=command.takes_args)
        return part

    def takes_args(self, name: str) -> bool:
        """Whether the command `name` (or alias) takes an argument."""
        return self._commands[self.resolve(name)].takes_args

    def resolve(self, name: str) -> str:
        """The canonical command name for `name` (aliases resolved)."""
        return self._aliases.get(name, name)

    def get_completions(self, prefix: str) -> list[str]:
        """Return sorted command names matching prefix."""
        all_names = sorted(set(self._commands) | set(self._aliases))
        return [n for n in all_names if n.startswith(prefix)]

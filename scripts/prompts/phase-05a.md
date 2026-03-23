You are building vimtg — a TUI-based MTG deck builder. This is Phase 5a: Ex command parser, registry, and core command handlers.

Read `PROGRESS.md` and existing source files for context. The TUI has NORMAL, INSERT modes working.

## 1. Command Parser — `src/vimtg/editor/commands.py`

```python
@dataclass(frozen=True)
class CommandRange:
    start: int | None   # Line number (0-indexed) or None for current
    end: int | None      # End line or None for single line
    is_whole_file: bool  # True for %

    @staticmethod
    def parse(range_str: str, cursor_row: int, buffer: Buffer) -> "CommandRange":
        """Parse vim range syntax:
        ''       → current line
        '%'      → whole file (0, last_line)
        '.'      → current line
        '$'      → last line
        'N'      → line N (1-indexed in input, convert to 0-indexed)
        'N,M'    → range [N, M]
        "'<,'>"  → visual selection range
        """

@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: str
    range: CommandRange | None
    bang: bool  # True if ! suffix (e.g., :q!)

def parse_command(input_str: str, cursor_row: int, buffer: Buffer) -> ParsedCommand:
    """Parse a full ex command string.
    Examples:
      ':w'           → ParsedCommand(name='w', args='', range=None, bang=False)
      ':5,10sort cmc' → ParsedCommand(name='sort', args='cmc', range=CommandRange(4,9), bang=False)
      ':q!'          → ParsedCommand(name='q', args='', range=None, bang=True)
      ':%s/a/b/g'    → ParsedCommand(name='s', args='a/b/g', range=whole_file, bang=False)
    """
```

## 2. Command Registry — `src/vimtg/editor/commands.py` (same file)

```python
CommandHandler = Callable[[Buffer, Cursor, ParsedCommand, "EditorContext"], tuple[Buffer, Cursor, str]]

class CommandRegistry:
    """Registry of ex commands. Commands return (new_buffer, new_cursor, message)."""

    def register(self, name: str, handler: CommandHandler, aliases: list[str] | None = None) -> None: ...
    def execute(self, cmd: ParsedCommand, buffer: Buffer, cursor: Cursor, ctx: "EditorContext") -> tuple[Buffer, Cursor, str]: ...
    def get_completions(self, prefix: str) -> list[str]: ...

@dataclass
class EditorContext:
    """Shared context passed to command handlers for I/O operations."""
    deck_service: DeckService
    search_service: SearchService
    file_path: Path | None
    modified: bool
```

## 3. Core Command Handlers — `src/vimtg/editor/command_handlers/`

### Buffer commands — `buffer_cmds.py`

```python
def cmd_write(buffer, cursor, cmd, ctx) -> tuple[Buffer, Cursor, str]:
    """:w [filename] — Save deck. Returns message like 'written burn.deck (40 cards)'."""

def cmd_quit(buffer, cursor, cmd, ctx) -> tuple[Buffer, Cursor, str]:
    """:q — Quit. Returns 'quit' signal. If modified and no !, return error message."""

def cmd_write_quit(buffer, cursor, cmd, ctx) -> tuple[Buffer, Cursor, str]:
    """:wq — Save and quit."""

def cmd_edit(buffer, cursor, cmd, ctx) -> tuple[Buffer, Cursor, str]:
    """:e [filename] — Open a file. If no filename, reload current."""

def cmd_enew(buffer, cursor, cmd, ctx) -> tuple[Buffer, Cursor, str]:
    """:enew — Open empty buffer."""
```

### Sort command — `sort.py`

```python
def cmd_sort(buffer, cursor, cmd, ctx) -> tuple[Buffer, Cursor, str]:
    """:sort [field] — Sort cards within range (or current section if no range).

    Fields:
      name   — alphabetical by card name (default)
      cmc    — by converted mana cost (requires card resolution)
      type   — by type line
      color  — by color (WUBRG order)
      price  — by price (requires card resolution)
      qty    — by quantity

    :sort!  — reverse sort
    :5,10sort cmc — sort lines 5-10 by CMC

    If no range specified, sort the entire current section (cards between comments/blanks).
    Only sorts card entry lines — comments, blanks, metadata stay in place.
    """
```

Implementation: Extract card lines from range, sort them, put them back. Non-card lines stay anchored.

### Deck commands — `deck_cmds.py`

```python
def cmd_stats(buffer, cursor, cmd, ctx) -> tuple[Buffer, Cursor, str]:
    """:stats — Toggle analytics overlay (Phase 7 placeholder). For now, print card count."""

def cmd_validate(buffer, cursor, cmd, ctx) -> tuple[Buffer, Cursor, str]:
    """:validate — Run deck validation, show results as messages."""

def cmd_export(buffer, cursor, cmd, ctx) -> tuple[Buffer, Cursor, str]:
    """:export [format] [filename] — Export deck (Phase 9 placeholder)."""
```

### Search commands — `search_cmds.py`

```python
def cmd_search(buffer, cursor, cmd, ctx) -> tuple[Buffer, Cursor, str]:
    """:search query — Search for cards, show results as temporary overlay or message.
    For now, print top 5 matches as message."""

def cmd_find(buffer, cursor, cmd, ctx) -> tuple[Buffer, Cursor, str]:
    """:find pattern — Jump to next card matching pattern in current buffer.
    Like vim's / search but for card names."""
```

## 4. Register commands in the app

In `VimTGApp` or `MainScreen` initialization:
```python
registry = CommandRegistry()
register_buffer_commands(registry)
register_sort_commands(registry)
register_deck_commands(registry)
register_search_commands(registry)
```

## 5. Wire COMMAND mode — extend `MainScreen`

When user presses `:`:
1. Mode transitions to COMMAND
2. CommandLine widget shows with `:` prefix
3. Keystrokes go to CommandLine (accumulate text)
4. Tab triggers completion from CommandRegistry
5. Enter: parse command, execute handler, show message, return to NORMAL
6. Escape: cancel, return to NORMAL

Display feedback messages in vim style:
- Success: `"burn.deck" written, 40 cards` (dim text at bottom)
- Error: `E37: No write since last change (add ! to override)` (red text)

## Tests — TDD

`tests/editor/test_commands.py`:
- `test_parse_simple` — `:w` → name="w", no args
- `test_parse_with_args` — `:sort cmc` → name="sort", args="cmc"
- `test_parse_range` — `:5,10sort` → range=(4,9), name="sort"
- `test_parse_whole_file` — `:%s/a/b/g` → range.is_whole_file=True
- `test_parse_bang` — `:q!` → bang=True
- `test_parse_dollar` — `:$` → range with end line
- `test_registry_execute` — registered command executes correctly
- `test_registry_completions` — prefix "so" returns ["sort"]

`tests/editor/command_handlers/test_sort.py`:
- `test_sort_by_name` — alphabetical ordering
- `test_sort_by_cmc` — numeric ordering by mana cost
- `test_sort_reverse` — :sort! reverses
- `test_sort_range` — only sorts specified line range
- `test_sort_preserves_comments` — comments stay in place
- `test_sort_section_default` — no range sorts current section only

`tests/editor/command_handlers/test_buffer_cmds.py`:
- `test_write_saves_file` — :w writes to disk
- `test_quit_unmodified` — :q succeeds if not modified
- `test_quit_modified_fails` — :q fails if modified
- `test_quit_bang_forces` — :q! succeeds even if modified
- `test_write_quit` — :wq saves then signals quit

## IMPORTANT

- Command feedback uses vim-style messages — not Rich panels or dialogs
- Error messages follow vim convention: `E{number}: message`
- Sort operates on SECTIONS by default, not the whole file — this is deck-aware behavior
- The CommandRegistry is the extensibility point — future phases add commands here
- All command handlers are pure functions: (state_in) → (state_out, message)
- Keep files under 200 lines

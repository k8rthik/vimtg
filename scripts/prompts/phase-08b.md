You are building vimtg — a TUI-based MTG deck builder. This is Phase 8b: Multi-buffer, dot repeat, macros, and text objects.

Read `PROGRESS.md` and existing source files for context.

## 1. Multi-Buffer Support

### Buffer Manager — `src/vimtg/editor/buffer_manager.py`

```python
@dataclass(frozen=True)
class BufferEntry:
    buffer: Buffer
    cursor: Cursor
    file_path: Path | None
    modified: bool
    history_service: HistoryService

class BufferManager:
    """Manages multiple open deck buffers (like vim's buffer list)."""

    def __init__(self) -> None: ...

    @property
    def current(self) -> BufferEntry: ...

    @property
    def current_index(self) -> int: ...

    def open(self, path: Path, buffer: Buffer) -> int:
        """Open a new buffer. Returns buffer index."""

    def close(self, index: int | None = None) -> BufferEntry | None:
        """Close buffer at index (or current). Returns closed entry or None if last buffer."""

    def switch_to(self, index: int) -> BufferEntry: ...
    def next(self) -> BufferEntry: ...
    def prev(self) -> BufferEntry: ...

    def update_current(self, buffer: Buffer, cursor: Cursor, modified: bool = True) -> None:
        """Update the current buffer's state."""

    def list_buffers(self) -> list[tuple[int, str, bool]]:
        """Return (index, filename, modified) for all buffers."""

    def for_each(self, fn: Callable[[BufferEntry], BufferEntry]) -> None:
        """Execute function on each buffer (for :bufdo)."""
```

### Tab Bar Widget — `src/vimtg/tui/widgets/tab_bar.py`

```python
class TabBar(Static):
    """Shows open buffer tabs at top of screen.

    Rendering:
      [burn.deck] [control.deck+] [new.deck]
    + indicates modified. Current tab is highlighted.
    Only shown when >1 buffer is open.
    """
```

### Buffer commands — extend `buffer_cmds.py`

```python
def cmd_edit_file(buffer, cursor, cmd, ctx):
    """:e filename.deck — Open file in new buffer (or switch if already open)."""

def cmd_buffer_next(buffer, cursor, cmd, ctx):
    """:bn — Switch to next buffer."""

def cmd_buffer_prev(buffer, cursor, cmd, ctx):
    """:bp — Switch to previous buffer."""

def cmd_buffer_delete(buffer, cursor, cmd, ctx):
    """:bd — Close current buffer (prompt if modified, :bd! forces)."""

def cmd_buffers(buffer, cursor, cmd, ctx):
    """:buffers — List open buffers:
      1  burn.deck [+]
      2 %control.deck
      3  new.deck
    % marks current buffer, + marks modified."""

def cmd_bufdo(buffer, cursor, cmd, ctx):
    """:bufdo cmd — Execute command on all buffers.
    Example: :bufdo %s/Scalding Tarn/Polluted Delta/g
    Switches to each buffer, runs command, switches back."""
```

Normal mode bindings:
- `gt` → next buffer (like vim's next tab)
- `gT` → previous buffer

## 2. Dot Repeat — `src/vimtg/editor/dot_repeat.py`

```python
@dataclass(frozen=True)
class RepeatableAction:
    """Captures a complete repeatable action for dot repeat."""
    action_type: str          # "operator", "insert", "command", "special"
    operator: str | None      # "d", "y", "c", "+", "-"
    motion: str | None        # "j", "w", "}", etc.
    count: int
    register: str | None
    inserted_text: str | None  # Text entered during insert (for 'c' and 'i' then text)
    command: str | None        # Ex command string (for :commands)

class DotRepeat:
    """Tracks and replays the last repeatable change."""

    def __init__(self) -> None: ...

    def record(self, action: RepeatableAction) -> None:
        """Record action as the last change."""

    def replay(self, buffer: Buffer, cursor: Cursor, register_store: RegisterStore) -> tuple[Buffer, Cursor, RegisterStore] | None:
        """Replay last recorded action. Returns new state or None if no action recorded."""

    @property
    def last_action(self) -> RepeatableAction | None: ...
```

### What is repeatable

- Operator actions: `dd`, `dw`, `yy`, `3dd`, `d}`
- Insert then text: `oLightning Bolt<Esc>` → dot inserts "Lightning Bolt" on new line
- Quantity changes: `+`, `-`
- Ex commands that modify buffer: `:sort`, `:s/...`

### What is NOT repeatable

- Motions without operators (j, k, gg)
- Mode switches alone
- Undo/redo
- Read-only commands (:buffers, :stats)

## 3. Macros — `src/vimtg/editor/macros.py`

```python
@dataclass(frozen=True)
class Macro:
    keys: tuple[str, ...]  # Recorded key sequence

class MacroRecorder:
    """Records and plays back key sequences."""

    def __init__(self) -> None: ...

    @property
    def is_recording(self) -> bool: ...

    @property
    def recording_register(self) -> str | None: ...

    def start_recording(self, register: str) -> None:
        """Start recording keys into register (a-z)."""

    def stop_recording(self) -> Macro:
        """Stop recording. Returns the recorded macro."""

    def record_key(self, key: str) -> None:
        """Record a keystroke (called on every key while recording)."""

    def get(self, register: str) -> Macro | None:
        """Get macro from register."""

    def play(self, register: str) -> tuple[str, ...] | None:
        """Get key sequence for playback. Returns None if register empty."""
```

### Macro flow

1. `qa` → start recording into register `a`
2. All keys are recorded AND executed normally
3. `q` → stop recording
4. `@a` → replay the recorded keys
5. `@@` → replay last played macro
6. `5@a` → replay 5 times

Status line shows `recording @a` while recording.

### Implementation

Macro playback feeds recorded keys back through the KeyMap as if typed. The MainScreen has a `_replay_keys(keys)` method that processes each key through the normal dispatch.

## 4. Text Objects — `src/vimtg/editor/text_objects.py`

Deck-specific text objects for use with operators.

```python
def text_object_inner_card(cursor: Cursor, buffer: Buffer) -> tuple[int, int] | None:
    """iw — Inner card: just the card name portion of the line.
    For '4 Lightning Bolt', the range covers the full line (since we're line-wise)."""

def text_object_around_card(cursor: Cursor, buffer: Buffer) -> tuple[int, int] | None:
    """aw — Around card: same as inner for line-wise operations."""

def text_object_inner_section(cursor: Cursor, buffer: Buffer) -> tuple[int, int] | None:
    """ip — Inner section: all card lines in the current section (between blank/comment lines).
    Does NOT include the section header comment or surrounding blank lines."""

def text_object_around_section(cursor: Cursor, buffer: Buffer) -> tuple[int, int] | None:
    """ap — Around section: card lines PLUS the section header and trailing blank line."""

TEXT_OBJECT_REGISTRY: dict[str, Callable] = {
    "iw": text_object_inner_card,
    "aw": text_object_around_card,
    "ip": text_object_inner_section,
    "ap": text_object_around_section,
}
```

Text objects work with operators:
- `dap` → delete entire section (including header)
- `dip` → delete section contents (keep header)
- `yap` → yank entire section
- `cip` → change section contents (delete and enter INSERT)

### Keymap integration

Update KeyMap to recognize two-char text objects after operators:
- After `d`, if next two chars are `a`+`p`, resolve text object and execute operator on range
- State: OPERATOR → TEXT_OBJECT_FIRST (i or a) → TEXT_OBJECT_SECOND (w, p)

## Tests — TDD

`tests/editor/test_dot_repeat.py`:
- `test_repeat_delete` — dd then . deletes next line
- `test_repeat_insert` — o+text+Esc then . inserts same text
- `test_repeat_quantity` — + then . increments again
- `test_repeat_with_count` — 3dd then . deletes 3 more
- `test_no_repeat_motion` — j is not recorded

`tests/editor/test_macros.py`:
- `test_record_and_play` — record qa...q, play @a
- `test_replay_last` — @@ replays last macro
- `test_count_replay` — 5@a replays 5 times
- `test_recording_status` — is_recording is True during recording
- `test_empty_register` — play returns None

`tests/editor/test_text_objects.py`:
- `test_inner_section` — correct range for ip
- `test_around_section` — includes header and trailing blank
- `test_section_at_start` — first section
- `test_section_at_end` — last section
- `test_cursor_on_comment` — returns None (not in a section)

`tests/editor/test_buffer_manager.py`:
- `test_open_buffer` — new buffer added
- `test_switch_buffer` — switch preserves state
- `test_close_buffer` — removes from list
- `test_next_prev` — cycles through buffers
- `test_bufdo` — runs command on all

## IMPORTANT

- Multi-buffer with :bufdo enables cross-deck operations — the killer workflow
- Dot repeat tracks the COMPLETE action (operator + motion + text) not just the last key
- Macros are key-sequence replay — they go through the normal KeyMap dispatch
- Text objects are deck-semantic: sections are the natural grouping unit
- Tab bar only shows when >1 buffer is open (don't waste space)
- Keep files under 200 lines each

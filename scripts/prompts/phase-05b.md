You are building vimtg — a TUI-based MTG deck builder. This is Phase 5b: Operators, registers, visual mode, and marks.

Read `PROGRESS.md` and existing source files for context. Phase 5a added the ex command system.

## 1. Operators — `src/vimtg/editor/operators.py`

Extend the existing file (which has increment/decrement from Phase 4).

```python
@dataclass(frozen=True)
class OperatorResult:
    buffer: Buffer
    cursor: Cursor
    yanked_text: tuple[str, ...] | None  # Lines that were yanked/deleted
    entered_insert: bool  # True for 'c' operator

def delete_lines(buffer: Buffer, start: int, end: int) -> tuple[Buffer, tuple[str, ...]]:
    """Delete lines [start, end] inclusive. Returns (new_buffer, deleted_lines)."""

def yank_lines(buffer: Buffer, start: int, end: int) -> tuple[str, ...]:
    """Copy lines [start, end] without modifying buffer."""

def put_lines(buffer: Buffer, cursor: Cursor, lines: tuple[str, ...], above: bool = False) -> tuple[Buffer, Cursor]:
    """Insert lines below (p) or above (P) cursor. Returns (new_buffer, new_cursor)."""

def execute_operator(
    op: str, buffer: Buffer, cursor: Cursor, motion: str | None,
    count: int, register_store: "RegisterStore"
) -> OperatorResult:
    """Execute a vim operator with motion.

    Resolves the motion to a line range, then applies the operator:
    - 'd' + motion → delete range, store in register
    - 'y' + motion → yank range to register
    - 'c' + motion → delete range, store in register, signal INSERT mode
    - 'dd' → delete current line
    - 'yy' → yank current line
    - 'cc' → change current line

    For line-wise operations (which all deck operations are):
    the range is [cursor.row, target.row] inclusive.
    """
```

### Operator-motion resolution

Given operator `d` and motion `j`: execute motion `j` from cursor to get target position. The range is min(cursor.row, target.row) to max(cursor.row, target.row).

Special cases:
- `dd`, `yy`, `cc` → range is just current line
- `d}` → delete from cursor to end of section
- `y{` → yank from cursor to start of section
- `dG` → delete from cursor to end of file
- `dgg` → delete from cursor to start of file

## 2. Registers — `src/vimtg/editor/registers.py`

```python
@dataclass(frozen=True)
class Register:
    content: tuple[str, ...]
    is_linewise: bool = True

class RegisterStore:
    """Vim register storage. Immutable operations return new stores."""

    def __init__(self) -> None:
        # Initialize with empty registers
        self._registers: dict[str, Register] = {}

    def get(self, name: str) -> Register:
        """Get register by name. Unknown register returns empty."""

    def set(self, name: str, content: tuple[str, ...], linewise: bool = True) -> "RegisterStore":
        """Return new RegisterStore with register set.
        Uppercase names append to the lowercase register.
        Setting unnamed '"' also sets '0' for yanks or shifts '1'-'9' for deletes."""

    def set_unnamed(self, content: tuple[str, ...], is_delete: bool = False) -> "RegisterStore":
        """Set unnamed register '"'. If delete, shift numbered registers 1-9."""

    @property
    def unnamed(self) -> Register:
        """The unnamed register (")."""

    def yank_register(self) -> Register:
        """Register 0 (last yank)."""
```

Register names:
- `"` — unnamed (default for all yank/delete)
- `0` — last yank
- `1`-`9` — delete history (1 = most recent, shifted on each delete)
- `a`-`z` — named (user-specified with `"a`)
- `A`-`Z` — append to named register
- `_` — black hole (discard)
- `+` — system clipboard (placeholder, implement OSC52 later)

## 3. Visual Mode — extend modes and MainScreen

### Visual selection state

```python
@dataclass(frozen=True)
class VisualSelection:
    anchor: int  # Line where visual mode started
    cursor: int  # Current cursor line

    @property
    def start(self) -> int: return min(self.anchor, self.cursor)

    @property
    def end(self) -> int: return max(self.anchor, self.cursor)

    @property
    def line_count(self) -> int: return self.end - self.start + 1
```

### Visual mode behavior

- `v` enters VISUAL mode (for decks, this is effectively line-wise since we operate on card entries)
- `V` enters VISUAL_LINE mode (same behavior for decks)
- Motions (j/k/G/gg/{/}) extend selection from anchor to new cursor
- Selection is highlighted in DeckView (background color on selected lines)
- `d` → delete selection, store in register, exit to NORMAL
- `y` → yank selection, exit to NORMAL
- `:` → enter COMMAND with range auto-filled to `'<,'>`
- `Escape` → exit to NORMAL, clear selection
- Status line shows `-- VISUAL --` or `-- V-LINE --` and selection count

### DeckView updates

Add visual selection highlighting:
```python
def _render_line(self, line_idx, buf_line, selection=None):
    if selection and selection.start <= line_idx <= selection.end:
        # Apply selection background color
```

## 4. Marks — `src/vimtg/editor/marks.py`

```python
@dataclass(frozen=True)
class Mark:
    row: int
    col: int

class MarkStore:
    """Store for vim marks."""

    def __init__(self) -> None:
        self._marks: dict[str, Mark] = {}

    def set(self, name: str, row: int, col: int = 0) -> "MarkStore":
        """Set mark. Returns new MarkStore. Names: a-z (buffer local)."""

    def get(self, name: str) -> Mark | None:
        """Get mark by name."""

    def set_special(self, name: str, row: int, col: int = 0) -> "MarkStore":
        """Set special marks: '.' (last change), '<' '>' (visual bounds), '' (last jump)."""

    def update_for_insert(self, line: int, count: int) -> "MarkStore":
        """Adjust marks after lines inserted. Marks below line shift down."""

    def update_for_delete(self, start: int, end: int) -> "MarkStore":
        """Adjust marks after lines deleted. Marks in range cleared, below shift up."""
```

Keybindings:
- `m{a-z}` → set mark at cursor
- `'{a-z}` → jump to mark (beginning of line)
- `''` → jump to last jump position

## 5. Wire everything into MainScreen

Update the action dispatch in MainScreen to handle:
- Operators (d, y, c, p, P, x) with register support
- Visual mode selection and operations
- Mark setting and jumping
- Status line updates for visual mode

## Tests — TDD

`tests/editor/test_operators.py`:
- `test_delete_single_line` — dd removes line, returns deleted text
- `test_delete_range` — d3j removes 4 lines
- `test_yank_line` — yy copies without modifying buffer
- `test_put_below` — p inserts yanked lines below cursor
- `test_put_above` — P inserts above
- `test_change_enters_insert` — cc deletes and signals insert mode
- `test_delete_section` — d} deletes to end of section
- `test_operator_with_count` — 3dd deletes 3 lines

`tests/editor/test_registers.py`:
- `test_unnamed_register` — delete stores in "
- `test_named_register` — "ayy stores in a
- `test_append_register` — "Ayy appends to a
- `test_numbered_shift` — deletes shift through 1-9
- `test_yank_register_0` — yank stores in 0
- `test_black_hole` — "_dd doesn't store
- `test_get_empty_register` — returns empty tuple

`tests/editor/test_marks.py`:
- `test_set_and_get` — ma then 'a returns correct position
- `test_mark_not_set` — returns None
- `test_marks_shift_on_insert` — marks below insert point shift
- `test_marks_shift_on_delete` — marks adjust after deletion
- `test_special_marks` — dot mark tracks last change

## IMPORTANT

- All deck operations are LINE-WISE — we don't do character-level operations (it's a deck editor, not a text editor)
- Operators compose with motions: d + j, y + }, c + w — this is the vim power
- Registers make cut/paste powerful: yank creature section to "a, paste into another deck
- Visual mode shows line count in status: `-- VISUAL -- 5 lines selected`
- All state objects (RegisterStore, MarkStore) are immutable — operations return new instances

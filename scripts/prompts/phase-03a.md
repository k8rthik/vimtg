You are building vimtg — a TUI-based MTG deck builder. This is Phase 3a: Buffer, Cursor, and Motion system.

Read `PROGRESS.md` and existing source files for context. The editor/ layer must be completely TUI-agnostic — pure Python, no Textual imports.

## 1. Buffer — `src/vimtg/editor/buffer.py`

The Buffer is the central abstraction bridging vim editing and deck semantics. It wraps the deck as a list of text lines with type classification.

```python
class LineType(Enum):
    COMMENT = "comment"           # // anything
    SECTION_HEADER = "section"    # // Creatures, // Spells, etc.
    CARD_ENTRY = "card"           # 4 Lightning Bolt
    SIDEBOARD_ENTRY = "sideboard" # SB: 2 Rest in Peace
    COMMANDER_ENTRY = "commander" # CMD: 1 Atraxa
    BLANK = "blank"               # empty line
    METADATA = "metadata"         # // Deck: Name, // Format: modern

@dataclass(frozen=True)
class BufferLine:
    text: str
    line_type: LineType

class Buffer:
    """Immutable deck-as-text-buffer. All mutation methods return new Buffer instances."""

    def __init__(self, lines: tuple[BufferLine, ...]) -> None: ...

    @staticmethod
    def from_text(text: str) -> "Buffer":
        """Parse raw text into classified lines."""

    def to_text(self) -> str:
        """Join lines back to text."""

    def line_count(self) -> int: ...
    def get_line(self, n: int) -> BufferLine: ...
    def get_lines(self) -> tuple[BufferLine, ...]: ...

    def set_line(self, n: int, text: str) -> "Buffer":
        """Return new Buffer with line n replaced. Re-classifies the line."""

    def insert_line(self, n: int, text: str) -> "Buffer":
        """Return new Buffer with new line inserted at position n."""

    def delete_lines(self, start: int, end: int) -> tuple["Buffer", tuple[str, ...]]:
        """Return (new_buffer, deleted_line_texts). Range is inclusive."""

    def append_line(self, text: str) -> "Buffer": ...

    def to_deck(self) -> "Deck":
        """Parse structured Deck from buffer lines. Uses deck_repository.parse_deck_text."""

    def card_name_at(self, line: int) -> str | None:
        """Extract card name from a card/sideboard entry line. None if not a card line."""

    def quantity_at(self, line: int) -> int | None:
        """Extract quantity from a card/sideboard entry line."""

    def is_card_line(self, line: int) -> bool:
        """True if line is CARD_ENTRY or SIDEBOARD_ENTRY."""

    def next_card_line(self, from_line: int) -> int | None:
        """Find next card entry line after from_line."""

    def prev_card_line(self, from_line: int) -> int | None:
        """Find previous card entry line before from_line."""

    def section_range(self, line: int) -> tuple[int, int] | None:
        """Find the start and end lines of the section containing line.
        A section is a group of consecutive card entries between blank/comment lines."""
```

### Line classification logic

- Starts with `//` → COMMENT (or SECTION_HEADER if matches known headers like "Creatures", "Spells", "Lands", "Sideboard", "Enchantments", "Artifacts", "Planeswalkers", "Instants", "Sorceries")
- Metadata pattern: `// Key: Value` where Key is Deck/Format/Author/Description → METADATA
- Starts with `SB:` → SIDEBOARD_ENTRY
- Starts with `CMD:` → COMMANDER_ENTRY
- Matches `^\d+\s+.+` → CARD_ENTRY
- Empty/whitespace only → BLANK

## 2. Cursor — `src/vimtg/editor/cursor.py`

```python
@dataclass(frozen=True)
class Cursor:
    row: int
    col: int

    def move(self, row_delta: int = 0, col_delta: int = 0, buffer: Buffer | None = None) -> "Cursor":
        """Return new Cursor with deltas applied, clamped to buffer bounds."""

    def clamp(self, buffer: Buffer) -> "Cursor":
        """Return new Cursor clamped to valid buffer position."""

    def move_to(self, row: int, col: int = 0) -> "Cursor": ...
```

All methods return NEW Cursor. Never mutate.

## 3. Motions — `src/vimtg/editor/motions.py`

Each motion is a function: `(cursor: Cursor, buffer: Buffer, count: int) -> Cursor`

```python
# Basic movement
def motion_down(cursor, buffer, count=1) -> Cursor:     # j
def motion_up(cursor, buffer, count=1) -> Cursor:       # k
def motion_left(cursor, buffer, count=1) -> Cursor:     # h
def motion_right(cursor, buffer, count=1) -> Cursor:    # l

# Line navigation
def motion_line_start(cursor, buffer, count=1) -> Cursor:  # 0
def motion_line_end(cursor, buffer, count=1) -> Cursor:    # $
def motion_first_line(cursor, buffer, count=1) -> Cursor:  # gg
def motion_last_line(cursor, buffer, count=1) -> Cursor:   # G
def motion_goto_line(cursor, buffer, count) -> Cursor:      # {count}G

# Deck-semantic motions (what makes vimtg special)
def motion_next_card(cursor, buffer, count=1) -> Cursor:       # w — next card entry
def motion_prev_card(cursor, buffer, count=1) -> Cursor:       # b — prev card entry
def motion_next_section(cursor, buffer, count=1) -> Cursor:    # } — next section
def motion_prev_section(cursor, buffer, count=1) -> Cursor:    # { — prev section
def motion_section_first(cursor, buffer, count=1) -> Cursor:   # [[ — first card in section
def motion_section_last(cursor, buffer, count=1) -> Cursor:    # ]] — last card in section

# Screen-relative (these will use viewport info from TUI later)
def motion_half_page_down(cursor, buffer, count=1) -> Cursor:  # Ctrl-D
def motion_half_page_up(cursor, buffer, count=1) -> Cursor:    # Ctrl-U
```

Deck-semantic motions:
- `w` (next_card): skip to next line where `is_card_line()` is True
- `b` (prev_card): skip to previous card line
- `}` (next_section): jump to first card of the NEXT section (past blank/comment lines)
- `{` (prev_section): jump to first card of the PREVIOUS section

All motions respect count: `3j` moves down 3 lines.

Create a registry mapping motion names to functions:
```python
MOTION_REGISTRY: dict[str, Callable] = {
    "j": motion_down, "k": motion_up, "h": motion_left, "l": motion_right,
    "0": motion_line_start, "$": motion_line_end,
    "gg": motion_first_line, "G": motion_last_line,
    "w": motion_next_card, "b": motion_prev_card,
    "{": motion_prev_section, "}": motion_next_section,
    "ctrl_d": motion_half_page_down, "ctrl_u": motion_half_page_up,
}
```

## Tests — TDD

`tests/editor/test_buffer.py` (20+ cases):
- `test_from_text` — parse sample deck text, verify line count and types
- `test_to_text_roundtrip` — from_text then to_text preserves content
- `test_line_classification_comment` — `// Creatures` → SECTION_HEADER
- `test_line_classification_metadata` — `// Deck: Burn` → METADATA
- `test_line_classification_card` — `4 Lightning Bolt` → CARD_ENTRY
- `test_line_classification_sideboard` — `SB: 2 Rest` → SIDEBOARD_ENTRY
- `test_line_classification_blank` — empty → BLANK
- `test_set_line_returns_new` — original unchanged
- `test_insert_line` — line count increases by 1
- `test_delete_lines` — returns deleted text and shorter buffer
- `test_card_name_at` — extracts "Lightning Bolt" from "4 Lightning Bolt"
- `test_quantity_at` — extracts 4 from "4 Lightning Bolt"
- `test_is_card_line` — True for card, False for comment
- `test_next_card_line` — skips comments and blanks
- `test_prev_card_line` — skips backwards over non-card lines
- `test_section_range` — correct start/end for a section
- `test_empty_buffer` — edge case, no crash

`tests/editor/test_cursor.py`:
- `test_cursor_frozen` — cannot modify
- `test_move_clamped` — can't go below 0 or past buffer
- `test_move_to` — direct positioning

`tests/editor/test_motions.py` (15+ cases):
- `test_motion_down` — j moves down 1
- `test_motion_down_count` — 3j moves down 3
- `test_motion_down_at_bottom` — stays at last line
- `test_motion_up_at_top` — stays at line 0
- `test_motion_first_line` — gg goes to line 0
- `test_motion_last_line` — G goes to last line
- `test_motion_goto_line` — 5G goes to line 4 (0-indexed)
- `test_motion_next_card` — w skips comments and blanks
- `test_motion_prev_card` — b skips backwards
- `test_motion_next_section` — } jumps to next section
- `test_motion_prev_section` — { jumps to previous section
- `test_motion_next_card_at_end` — stays at last card
- `test_motion_prev_card_at_start` — stays at first card
- `test_motion_registry_complete` — all expected keys present

## IMPORTANT

- Buffer is IMMUTABLE — all methods return new instances
- No Textual imports — this is pure Python
- Motions are functions, not classes (simple, composable)
- Deck-semantic motions (w, b, {, }) are what make vimtg feel purpose-built, not generic
- Edge cases matter: empty buffer, single-line buffer, cursor at boundaries
- Keep each file under 200 lines

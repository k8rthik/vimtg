You are building vimtg — a TUI-based MTG deck builder. This is Phase 3b: Mode manager and key sequence parser.

Read `PROGRESS.md` and existing source files for context. Phase 3a created Buffer, Cursor, and Motions.

## 1. Mode Manager — `src/vimtg/editor/modes.py`

```python
class Mode(Enum):
    NORMAL = "NORMAL"
    INSERT = "INSERT"
    VISUAL = "VISUAL"
    VISUAL_LINE = "V-LINE"
    COMMAND = "COMMAND"
    SEARCH = "SEARCH"

# Valid transitions — anything not listed is illegal
TRANSITIONS: dict[Mode, set[Mode]] = {
    Mode.NORMAL: {Mode.INSERT, Mode.VISUAL, Mode.VISUAL_LINE, Mode.COMMAND, Mode.SEARCH},
    Mode.INSERT: {Mode.NORMAL},
    Mode.VISUAL: {Mode.NORMAL, Mode.VISUAL_LINE, Mode.COMMAND},
    Mode.VISUAL_LINE: {Mode.NORMAL, Mode.VISUAL, Mode.COMMAND},
    Mode.COMMAND: {Mode.NORMAL},
    Mode.SEARCH: {Mode.NORMAL},
}

@dataclass(frozen=True)
class ModeState:
    mode: Mode
    previous: Mode | None = None

class ModeManager:
    """Manages modal state transitions with callbacks."""

    def __init__(self) -> None: ...

    @property
    def current(self) -> Mode: ...

    @property
    def previous(self) -> Mode | None: ...

    def transition(self, target: Mode) -> Mode:
        """Transition to target mode. Returns new mode.
        Raises ValueError if transition is invalid."""

    def on_mode_change(self, callback: Callable[[Mode, Mode], None]) -> None:
        """Register callback(old_mode, new_mode) for mode changes."""

    def is_normal(self) -> bool: ...
    def is_insert(self) -> bool: ...
    def is_visual(self) -> bool: ...
    def is_command(self) -> bool: ...
```

## 2. Key Sequence Parser — `src/vimtg/editor/keymap.py`

This is the most complex part of the vim emulation. It parses multi-keystroke sequences into actions.

```python
class KeyResult(Enum):
    PENDING = "pending"       # Waiting for more keys (e.g., after 'd')
    COMPLETE = "complete"     # Full action ready to execute
    NO_MATCH = "no_match"     # Key sequence doesn't match anything

@dataclass(frozen=True)
class ParsedAction:
    """Result of parsing a complete vim key sequence."""
    action_type: str          # "motion", "operator", "mode_switch", "command", "special"
    action: str               # The specific action name (e.g., "j", "dd", "i", ":")
    count: int                # Repeat count (default 1)
    register: str | None      # Register name (e.g., "a" from "ayy)
    motion: str | None        # Motion for operator (e.g., "j" from "dj")
    text: str | None          # Accumulated text (for insert mode)

class KeyMap:
    """Vim key sequence state machine.

    Handles:
    - Simple keys: j, k, i, v, :
    - Count prefixes: 4j, 10k, 3dd
    - Operator-motion: dj, yy, d3j
    - Register prefix: "ayy, "ap
    - Multi-char keys: gg, dd, yy
    """

    def __init__(self, mode: Mode) -> None: ...

    def feed(self, key: str) -> tuple[KeyResult, ParsedAction | None]:
        """Feed a keystroke. Returns (result, action_or_none).

        State machine:
        1. If digit and no operator yet → accumulate count
        2. If " → next key is register name
        3. If operator key (d,y,c) → wait for motion
        4. If motion key → resolve immediately (or with pending operator)
        5. If mode switch key (i,v,:) → immediate action
        6. Multi-char: 'g' waits for next key (gg, gq, etc.)
        """

    def reset(self) -> None:
        """Clear all pending state."""

    def set_mode(self, mode: Mode) -> None:
        """Update the current mode (changes which keys are valid)."""
```

### Key bindings per mode

**NORMAL mode keys:**
```python
# Motions
"j", "k", "h", "l"           # basic movement
"0", "$"                       # line start/end
"gg", "G"                      # file start/end
"w", "b"                       # next/prev card
"{", "}"                       # next/prev section
"ctrl_d", "ctrl_u"            # half page

# Mode switches
"i"    → INSERT (at cursor)
"a"    → INSERT (after cursor)
"o"    → INSERT (new line below)
"O"    → INSERT (new line above)
"A"    → INSERT (end of line)
"v"    → VISUAL
"V"    → VISUAL_LINE
":"    → COMMAND
"/"    → SEARCH

# Operators (wait for motion or double-tap for line-wise)
"d"    → PENDING (delete: dd=line, dj=down, dw=next card, d}=section)
"y"    → PENDING (yank: yy=line, yj=down, yw=next card)
"c"    → PENDING (change: cc=line, enters INSERT after delete)

# Immediate actions
"p"    → put below
"P"    → put above
"x"    → delete card at cursor
"u"    → undo
"ctrl_r" → redo
"+"    → increment quantity
"-"    → decrement quantity
"."    → repeat last change
"q"    → start/stop macro recording (pending register key)
"@"    → play macro (pending register key)
"\""   → register prefix (pending register key)

# Special
"escape" → cancel pending, return to NORMAL
```

**INSERT mode keys:**
- All printable characters → accumulate text
- `escape` → NORMAL
- `backspace` → delete char
- `ctrl_n`, `ctrl_p` → next/prev search result (handled by TUI)
- `enter` → confirm card selection (handled by TUI)
- `tab` → autocomplete

**VISUAL mode keys:**
- Same motions as NORMAL (extend selection)
- `d` → delete selection
- `y` → yank selection
- `escape` → back to NORMAL
- `:` → COMMAND (with visual range)

**COMMAND mode keys:**
- All printable characters → accumulate command text
- `escape` → cancel, NORMAL
- `enter` → execute command
- `backspace` → delete char
- `tab` → autocomplete command
- `up/down` → command history

### State machine detail

The key parser has these states:
1. **IDLE** — waiting for first key
2. **COUNT** — accumulating digit prefix (e.g., after "4")
3. **REGISTER** — waiting for register name (after `"`)
4. **OPERATOR** — have operator, waiting for motion (after `d`, `y`, `c`)
5. **OPERATOR_COUNT** — have operator, accumulating motion count (e.g., `d3` waiting for motion)
6. **MULTI_KEY** — waiting for second key (after `g`, `z`, `[`, `]`)

Timeouts: if a key is ambiguous (like `g` which could start `gg` or `gq`), wait for next key. If escape arrives, cancel.

## Tests — TDD

`tests/editor/test_modes.py`:
- `test_initial_mode` — starts in NORMAL
- `test_valid_transition` — NORMAL→INSERT succeeds
- `test_invalid_transition` — INSERT→VISUAL raises ValueError
- `test_callback_called` — mode change triggers callback
- `test_previous_mode` — tracks last mode

`tests/editor/test_keymap.py` (20+ cases):
- `test_simple_motion` — "j" → COMPLETE, action="j"
- `test_count_motion` — "4" then "j" → COMPLETE, count=4, action="j"
- `test_mode_switch_i` — "i" → COMPLETE, action_type="mode_switch"
- `test_command_mode` — ":" → COMPLETE, action_type="mode_switch"
- `test_operator_motion` — "d" → PENDING, "j" → COMPLETE, action="d", motion="j"
- `test_operator_doubled` — "d" → PENDING, "d" → COMPLETE, action="dd"
- `test_operator_count_motion` — "d", "3", "j" → COMPLETE, count=3, motion="j"
- `test_count_operator_motion` — "3", "d", "j" → COMPLETE, count=3, action="d", motion="j"
- `test_register_yank` — '"', "a", "y", "y" → COMPLETE, register="a", action="yy"
- `test_multi_key_gg` — "g" → PENDING, "g" → COMPLETE, action="gg"
- `test_escape_cancels` — "d" → PENDING, "escape" → reset to IDLE
- `test_put` — "p" → COMPLETE, action="p"
- `test_undo` — "u" → COMPLETE, action="u"
- `test_increment` — "+" → COMPLETE, action="+"
- `test_insert_mode_text` — in INSERT, "a","b","c" → accumulate text
- `test_insert_mode_escape` — in INSERT, "escape" → COMPLETE, mode_switch to NORMAL
- `test_visual_mode_motion` — in VISUAL, "j" → COMPLETE, action="j"
- `test_visual_operator` — in VISUAL, "d" → COMPLETE, action="d" (operates on selection)
- `test_command_mode_text` — in COMMAND, ":sort cmc" → accumulate
- `test_command_enter` — in COMMAND, "enter" → COMPLETE with command text
- `test_reset_clears_state` — after partial sequence, reset returns to IDLE

## IMPORTANT

- The keymap is a state machine, NOT a lookup table. It must handle arbitrary combinations of count + register + operator + motion.
- Keep the state machine simple and testable. Avoid deep nesting — use explicit state transitions.
- No Textual imports — this is pure Python
- The ModeManager stores minimal state — it's mainly a validation layer
- Keep each file under 200 lines

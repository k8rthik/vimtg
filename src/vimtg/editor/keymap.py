"""Vim key sequence parser — state machine for multi-key commands.

TUI-agnostic: no Textual imports. Accepts string key names, returns
ParsedAction describing what should happen.
"""

from dataclasses import dataclass
from enum import Enum

from vimtg.editor.line_buffer import LineBuffer
from vimtg.editor.modes import Mode


class KeyResult(Enum):
    PENDING = "pending"
    COMPLETE = "complete"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class ParsedAction:
    action_type: str  # "motion", "operator", "mode_switch", "command_submit", "special"
    action: str  # e.g. "j", "dd", "i", ":"
    count: int = 1
    register: str | None = None
    motion: str | None = None
    text: str | None = None
    cursor_pos: int | None = None


class _State(Enum):
    IDLE = "idle"
    COUNT = "count"
    REGISTER = "register"
    OPERATOR = "operator"
    OPERATOR_COUNT = "operator_count"
    MULTI_KEY = "multi_key"


# Keys recognized in NORMAL mode
MOTIONS = frozenset(
    {"j", "k", "h", "l", "0", "$", "w", "b", "{", "}", "ctrl_d", "ctrl_u"}
)
OPERATORS = frozenset({"d", "y", "c"})
MODE_SWITCHES: dict[str, str] = {
    "i": "INSERT",
    "o": "INSERT",
    "O": "INSERT",
    "v": "VISUAL",
    "V": "VISUAL_LINE",
    ":": "COMMAND",
    "/": "SEARCH",
}
SPECIAL_KEYS = frozenset({"p", "P", "x", "u", "ctrl_r", "+", "-", ".", "?", "@"})
MULTI_KEY_STARTERS = frozenset({"g", "[", "]"})


def _apply_text_edit(
    buf: LineBuffer, key: str,
) -> tuple[LineBuffer, ParsedAction] | None:
    """Handle cursor movement and text editing keys shared by insert/command modes.

    Returns (new_buffer, action) for handled keys, or None for mode-specific keys.
    """
    if key == "backspace":
        buf = buf.delete_backward()
        return buf, ParsedAction("special", "backspace", text=buf.text, cursor_pos=buf.cursor)
    if key == "delete":
        buf = buf.delete_forward()
        return buf, ParsedAction("special", "delete", text=buf.text, cursor_pos=buf.cursor)
    if key == "left":
        buf = buf.move_left()
        return buf, ParsedAction("special", "cursor_move", text=buf.text, cursor_pos=buf.cursor)
    if key == "right":
        buf = buf.move_right()
        return buf, ParsedAction("special", "cursor_move", text=buf.text, cursor_pos=buf.cursor)
    if key == "home":
        buf = buf.move_home()
        return buf, ParsedAction("special", "cursor_move", text=buf.text, cursor_pos=buf.cursor)
    if key == "end":
        buf = buf.move_end()
        return buf, ParsedAction("special", "cursor_move", text=buf.text, cursor_pos=buf.cursor)
    if len(key) == 1:
        buf = buf.insert(key)
        return buf, ParsedAction("special", "char", text=buf.text, cursor_pos=buf.cursor)
    return None


class KeyMap:
    """State machine that parses vim key sequences into ParsedActions."""

    def __init__(self, mode: Mode = Mode.NORMAL) -> None:
        self._mode = mode
        self._state = _State.IDLE
        self._count_str = ""
        self._register: str | None = None
        self._operator: str | None = None
        self._operator_count_str = ""
        self._multi_key_prefix = ""
        self._insert_buf = LineBuffer()
        self._command_buf = LineBuffer()

    def set_mode(self, mode: Mode) -> None:
        self._mode = mode
        self.reset()

    def reset(self) -> None:
        self._state = _State.IDLE
        self._count_str = ""
        self._register = None
        self._operator = None
        self._operator_count_str = ""
        self._multi_key_prefix = ""

    def reset_text(self) -> None:
        self._insert_buf = LineBuffer()
        self._command_buf = LineBuffer()

    def set_command_text(self, text: str) -> None:
        """Replace the accumulated command text (used by Tab-accept)."""
        self._command_buf = LineBuffer.from_text(text)

    def set_insert_text(self, text: str) -> None:
        """Pre-fill the accumulated insert text (used by line-edit mode)."""
        self._insert_buf = LineBuffer.from_text(text)

    def feed(self, key: str) -> tuple[KeyResult, ParsedAction | None]:
        if self._mode == Mode.INSERT:
            return self._feed_insert(key)
        if self._mode in (Mode.COMMAND, Mode.SEARCH):
            return self._feed_command(key)
        if self._mode in (Mode.VISUAL, Mode.VISUAL_LINE):
            return self._feed_visual(key)
        return self._feed_normal(key)

    def _feed_normal(self, key: str) -> tuple[KeyResult, ParsedAction | None]:
        if key == "escape":
            self.reset()
            return KeyResult.COMPLETE, ParsedAction("special", "escape")

        if key == '"' and self._state == _State.IDLE:
            self._state = _State.REGISTER
            return KeyResult.PENDING, None
        if self._state == _State.REGISTER:
            self._register = key
            self._state = _State.IDLE
            return KeyResult.PENDING, None

        if key.isdigit() and key != "0" and self._state in (_State.IDLE, _State.COUNT):
            self._count_str += key
            self._state = _State.COUNT
            return KeyResult.PENDING, None
        if key.isdigit() and self._state == _State.OPERATOR:
            self._operator_count_str += key
            self._state = _State.OPERATOR_COUNT
            return KeyResult.PENDING, None
        if key.isdigit() and self._state == _State.OPERATOR_COUNT:
            self._operator_count_str += key
            return KeyResult.PENDING, None

        count = int(self._count_str) if self._count_str else 1

        if key in MULTI_KEY_STARTERS and self._state in (_State.IDLE, _State.COUNT):
            self._multi_key_prefix = key
            self._state = _State.MULTI_KEY
            return KeyResult.PENDING, None
        if self._state == _State.MULTI_KEY:
            full_key = self._multi_key_prefix + key
            if full_key in ("gg", "[[", "]]"):
                action = ParsedAction("motion", full_key, count, self._register)
                self.reset()
                return KeyResult.COMPLETE, action
            self.reset()
            return KeyResult.NO_MATCH, None

        if key in OPERATORS and self._state in (_State.IDLE, _State.COUNT):
            self._operator = key
            self._state = _State.OPERATOR
            return KeyResult.PENDING, None

        if self._state in (_State.OPERATOR, _State.OPERATOR_COUNT) and key == self._operator:
            op_count = int(self._operator_count_str) if self._operator_count_str else 1
            total_count = count * op_count
            action = ParsedAction("operator", key + key, total_count, self._register)
            self.reset()
            return KeyResult.COMPLETE, action

        if self._state in (_State.OPERATOR, _State.OPERATOR_COUNT):
            if key in MULTI_KEY_STARTERS:
                self._multi_key_prefix = key
                return KeyResult.PENDING, None
            if key in MOTIONS or key == "G":
                op_count = int(self._operator_count_str) if self._operator_count_str else 1
                total_count = count * op_count
                action = ParsedAction(
                    "operator", self._operator or "", total_count, self._register, motion=key
                )
                self.reset()
                return KeyResult.COMPLETE, action
            self.reset()
            return KeyResult.NO_MATCH, None

        if key in MOTIONS:
            action = ParsedAction("motion", key, count, self._register)
            self.reset()
            return KeyResult.COMPLETE, action
        if key == "G":
            g_count = count if self._count_str else 0
            action = ParsedAction("motion", "G", g_count, self._register)
            self.reset()
            return KeyResult.COMPLETE, action

        if key in MODE_SWITCHES:
            action = ParsedAction("mode_switch", key, count, self._register)
            self.reset()
            return KeyResult.COMPLETE, action

        if key in SPECIAL_KEYS:
            action = ParsedAction("special", key, count, self._register)
            self.reset()
            return KeyResult.COMPLETE, action

        self.reset()
        return KeyResult.NO_MATCH, None

    def _feed_insert(self, key: str) -> tuple[KeyResult, ParsedAction | None]:
        if key == "escape":
            text = self._insert_buf.text
            self._insert_buf = LineBuffer()
            return KeyResult.COMPLETE, ParsedAction("mode_switch", "escape", text=text)
        if key in ("ctrl_j", "ctrl_k", "tab", "shift_tab", "enter", "up", "down"):
            return KeyResult.COMPLETE, ParsedAction(
                "special", key,
                text=self._insert_buf.text, cursor_pos=self._insert_buf.cursor,
            )
        result = _apply_text_edit(self._insert_buf, key)
        if result is not None:
            self._insert_buf, action = result
            return KeyResult.COMPLETE, action
        return KeyResult.NO_MATCH, None

    def _feed_command(self, key: str) -> tuple[KeyResult, ParsedAction | None]:
        if key == "escape":
            self._command_buf = LineBuffer()
            return KeyResult.COMPLETE, ParsedAction("mode_switch", "escape")
        if key == "enter":
            text = self._command_buf.text
            self._command_buf = LineBuffer()
            return KeyResult.COMPLETE, ParsedAction("command_submit", "enter", text=text)
        if key in ("tab", "shift_tab"):
            return KeyResult.COMPLETE, ParsedAction(
                "special", key,
                text=self._command_buf.text, cursor_pos=self._command_buf.cursor,
            )
        result = _apply_text_edit(self._command_buf, key)
        if result is not None:
            self._command_buf, action = result
            return KeyResult.COMPLETE, action
        return KeyResult.NO_MATCH, None

    def _feed_visual(self, key: str) -> tuple[KeyResult, ParsedAction | None]:
        if key == "escape":
            return KeyResult.COMPLETE, ParsedAction("mode_switch", "escape")
        if key in ("d", "y", "c"):
            return KeyResult.COMPLETE, ParsedAction("operator", key)
        if key == ":":
            return KeyResult.COMPLETE, ParsedAction("mode_switch", ":")
        return self._feed_normal(key)

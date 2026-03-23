"""Vim key sequence parser — state machine for multi-key commands.

TUI-agnostic: no Textual imports. Accepts string key names, returns
ParsedAction describing what should happen.
"""

from dataclasses import dataclass
from enum import Enum

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


class _State(Enum):
    IDLE = "idle"
    COUNT = "count"
    REGISTER = "register"
    OPERATOR = "operator"
    OPERATOR_COUNT = "operator_count"
    MULTI_KEY = "multi_key"


# Keys recognized in NORMAL mode
MOTIONS = frozenset(
    {
        "j", "k", "h", "l", "0", "$", "w", "b",
        "{", "}", "left_curly_bracket", "right_curly_bracket",
        "ctrl_d", "ctrl_u",
    }
)
OPERATORS = frozenset({"d", "y", "c"})
MODE_SWITCHES: dict[str, str] = {
    "i": "INSERT",
    "a": "INSERT",
    "o": "INSERT",
    "O": "INSERT",
    "A": "INSERT",
    "v": "VISUAL",
    "V": "VISUAL_LINE",
    ":": "COMMAND",
    "/": "SEARCH",
}
SPECIAL_KEYS = frozenset({"p", "P", "x", "u", "ctrl_r", "+", "-", "."})
MULTI_KEY_STARTERS = frozenset({"g", "[", "]", "left_square_bracket", "right_square_bracket"})


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
        self._insert_text = ""
        self._command_text = ""

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
        self._insert_text = ""
        self._command_text = ""

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
            # Normalize Textual bracket names to symbols
            normalized = full_key
            normalized = normalized.replace("left_square_bracket", "[")
            normalized = normalized.replace("right_square_bracket", "]")
            if normalized in ("gg", "[[", "]]"):
                action = ParsedAction("motion", normalized, count, self._register)
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
            text = self._insert_text
            self._insert_text = ""
            return KeyResult.COMPLETE, ParsedAction("mode_switch", "escape", text=text)
        if key == "backspace":
            self._insert_text = self._insert_text[:-1]
            return KeyResult.COMPLETE, ParsedAction("special", "backspace", text=self._insert_text)
        if key in ("ctrl_n", "ctrl_p", "tab", "shift_tab", "enter", "up", "down"):
            return KeyResult.COMPLETE, ParsedAction("special", key, text=self._insert_text)
        if len(key) == 1:
            self._insert_text += key
            return KeyResult.COMPLETE, ParsedAction("special", "char", text=self._insert_text)
        return KeyResult.NO_MATCH, None

    def _feed_command(self, key: str) -> tuple[KeyResult, ParsedAction | None]:
        if key == "escape":
            self._command_text = ""
            return KeyResult.COMPLETE, ParsedAction("mode_switch", "escape")
        if key == "enter":
            text = self._command_text
            self._command_text = ""
            return KeyResult.COMPLETE, ParsedAction("command_submit", "enter", text=text)
        if key == "backspace":
            self._command_text = self._command_text[:-1]
            return KeyResult.COMPLETE, ParsedAction("special", "backspace", text=self._command_text)
        if key == "tab":
            return KeyResult.COMPLETE, ParsedAction("special", "tab", text=self._command_text)
        if len(key) == 1:
            self._command_text += key
            return KeyResult.COMPLETE, ParsedAction("special", "char", text=self._command_text)
        return KeyResult.NO_MATCH, None

    def _feed_visual(self, key: str) -> tuple[KeyResult, ParsedAction | None]:
        if key == "escape":
            return KeyResult.COMPLETE, ParsedAction("mode_switch", "escape")
        if key in ("d", "y", "c"):
            return KeyResult.COMPLETE, ParsedAction("operator", key)
        if key == ":":
            return KeyResult.COMPLETE, ParsedAction("mode_switch", ":")
        return self._feed_normal(key)

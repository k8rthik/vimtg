"""Vim mode management — TUI-agnostic, zero Textual imports."""

from collections.abc import Callable
from enum import Enum


class Mode(Enum):
    NORMAL = "NORMAL"
    INSERT = "INSERT"
    VISUAL = "VISUAL"
    VISUAL_LINE = "V-LINE"
    COMMAND = "COMMAND"
    SEARCH = "SEARCH"


VALID_TRANSITIONS: dict[Mode, frozenset[Mode]] = {
    Mode.NORMAL: frozenset(
        {Mode.INSERT, Mode.VISUAL, Mode.VISUAL_LINE, Mode.COMMAND, Mode.SEARCH}
    ),
    Mode.INSERT: frozenset({Mode.NORMAL}),
    Mode.VISUAL: frozenset({Mode.NORMAL, Mode.VISUAL_LINE, Mode.COMMAND}),
    Mode.VISUAL_LINE: frozenset({Mode.NORMAL, Mode.VISUAL, Mode.COMMAND}),
    Mode.COMMAND: frozenset({Mode.NORMAL}),
    Mode.SEARCH: frozenset({Mode.NORMAL}),
}

ModeChangeCallback = Callable[[Mode, Mode], None]


class ModeManager:
    """Manages vim mode state and transitions.

    Uses a whitelist of valid transitions to prevent illegal mode changes.
    Notifies registered callbacks on every transition.
    """

    def __init__(self) -> None:
        self._current = Mode.NORMAL
        self._previous: Mode | None = None
        self._callbacks: list[ModeChangeCallback] = []

    @property
    def current(self) -> Mode:
        return self._current

    @property
    def previous(self) -> Mode | None:
        return self._previous

    def transition(self, target: Mode) -> Mode:
        """Transition to target mode if valid, else raise ValueError."""
        allowed = VALID_TRANSITIONS.get(self._current, frozenset())
        if target not in allowed:
            msg = f"Invalid transition: {self._current} -> {target}"
            raise ValueError(msg)
        old = self._current
        self._previous = old
        self._current = target
        self._notify(old, target)
        return target

    def force_normal(self) -> None:
        """Force back to NORMAL from any mode (for Escape)."""
        if self._current != Mode.NORMAL:
            old = self._current
            self._previous = old
            self._current = Mode.NORMAL
            self._notify(old, Mode.NORMAL)

    def on_mode_change(self, callback: ModeChangeCallback) -> None:
        """Register a callback that fires on every mode transition."""
        self._callbacks.append(callback)

    def is_normal(self) -> bool:
        return self._current == Mode.NORMAL

    def is_insert(self) -> bool:
        return self._current == Mode.INSERT

    def is_visual(self) -> bool:
        return self._current in (Mode.VISUAL, Mode.VISUAL_LINE)

    def is_command(self) -> bool:
        return self._current == Mode.COMMAND

    def _notify(self, old: Mode, new: Mode) -> None:
        for cb in self._callbacks:
            cb(old, new)

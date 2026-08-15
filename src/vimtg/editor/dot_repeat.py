"""Dot-repeat tracking for the deck editor.

Records the last repeatable action so the '.' key can replay it.
Operator and quantity actions are repeatable — those are the two
action shapes the replay path (key_handler._replay_dot) implements.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass

# Action types that are repeatable via '.'
REPEATABLE_TYPES: frozenset[str] = frozenset({
    "operator",
    "quantity",
})


@dataclass(frozen=True)
class RepeatableAction:
    """A single action that can be replayed with '.'."""

    action_type: str  # "operator" or "quantity"
    operator: str | None = None
    motion: str | None = None
    count: int = 1
    register: str | None = None


class DotRepeat:
    """Stores the last repeatable action for dot-repeat."""

    def __init__(self) -> None:
        self._last: RepeatableAction | None = None

    def record(self, action: RepeatableAction) -> None:
        """Record an action if its type is repeatable."""
        if action.action_type in REPEATABLE_TYPES:
            self._last = action

    @property
    def last_action(self) -> RepeatableAction | None:
        """Return the last recorded repeatable action, or None."""
        return self._last

    def clear(self) -> None:
        """Reset the stored action."""
        self._last = None

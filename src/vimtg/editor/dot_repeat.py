"""Dot-repeat tracking for the deck editor.

Records the last repeatable change so the '.' key can replay it. Every
change the session can replay has an action type here; the replay
itself lives in session._replay_dot.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Action types that are repeatable via '.'
REPEATABLE_TYPES: frozenset[str] = frozenset({
    "operator",   # d/y/c + motion, dd, x; c also carries the card it inserted
    "quantity",   # + / -
    "zone",       # zs zm zd zc zp
    "board",      # zi zo
    "insert",     # o / O + the card confirmed in the search
    "put",        # p / P
    "tag",        # ta tr tt (text = tag), tc (clear)
    "category",   # gc (text = category), gC (text = None: clear)
    "comment",    # A (text = the comment)
    "line_edit",  # i (text = the edited value after any locked prefix)
    "ex",         # :s (text = the substitute's arguments)
})


@dataclass(frozen=True)
class RepeatableAction:
    """A single action that can be replayed with '.'.

    `lines` > 0 marks an action made on a visual selection: '.' replays
    it on that many lines from the cursor. `card` (a Card or None) and
    `quantity` describe the card an o/O/c inserted.
    """

    action_type: str
    operator: str | None = None
    motion: str | None = None
    count: int = 1
    register: str | None = None
    lines: int = 0
    text: str | None = None
    card_name: str | None = None
    card: Any = None
    quantity: int = 1


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

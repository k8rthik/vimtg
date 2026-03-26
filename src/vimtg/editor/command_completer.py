"""Command-line tab completion for ex commands.

Provides fuzzy prefix completion for :commands, cycling through matches
with Tab/Shift-Tab and showing ghost text for the best match.
"""

from __future__ import annotations

from dataclasses import dataclass

from vimtg.editor.commands import CommandRegistry


@dataclass(frozen=True)
class CompletionState:
    """Immutable snapshot of a completion session."""

    prefix: str
    matches: tuple[str, ...]
    selected: int = 0


class CommandCompleter:
    """Tab-completion engine for : command mode."""

    def __init__(self, registry: CommandRegistry) -> None:
        self._registry = registry

    def complete(self, text: str) -> CompletionState | None:
        """Start or update a completion for the given command text."""
        prefix = text.lstrip()
        if not prefix:
            return None
        matches = self._registry.get_completions(prefix)
        if not matches:
            return None
        return CompletionState(
            prefix=prefix,
            matches=tuple(matches),
            selected=0,
        )

    def current_ghost(self, state: CompletionState | None) -> str:
        """Return the ghost text (suffix) for the currently selected match."""
        if state is None or not state.matches:
            return ""
        match = state.matches[state.selected]
        if match.startswith(state.prefix):
            return match[len(state.prefix):]
        return ""

    def accept(self, state: CompletionState | None) -> str:
        """Return the full text of the currently selected match."""
        if state is None or not state.matches:
            return ""
        return state.matches[state.selected]

    def cycle_next(self, state: CompletionState | None) -> CompletionState | None:
        """Move to the next completion match."""
        if state is None or not state.matches:
            return state
        new_idx = (state.selected + 1) % len(state.matches)
        return CompletionState(
            prefix=state.prefix,
            matches=state.matches,
            selected=new_idx,
        )

    def cycle_prev(self, state: CompletionState | None) -> CompletionState | None:
        """Move to the previous completion match."""
        if state is None or not state.matches:
            return state
        new_idx = (state.selected - 1) % len(state.matches)
        return CompletionState(
            prefix=state.prefix,
            matches=state.matches,
            selected=new_idx,
        )

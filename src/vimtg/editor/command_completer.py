"""Fuzzy command-line completion for ex commands.

Splits a typed command into a vim-style range prefix (e.g. ``%``, ``5,10``,
``.``) and a typed command name, then ranks registered commands by a small
fuzzy score: prefix matches are preferred (negative scores), subsequence
matches fall back to a positive score based on character gaps and first-match
position. Cycling and ghost rendering operate on immutable :class:`CompletionState`
snapshots so the TUI layer stays stateless.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vimtg.editor.commands import CommandRegistry

_RANGE_PATTERN = re.compile(r"^([^a-zA-Z_]*)(.*)$")


def fuzzy_score(query: str, candidate: str) -> int | None:
    """Score ``candidate`` against ``query``. Lower is better; ``None`` means no match.

    - Empty query matches everything with score 0.
    - Prefix matches return ``-len(query)`` (preferred over subsequence).
    - Subsequence matches return ``first_pos + sum(gaps)`` where gaps count the
      characters skipped between consecutive matched positions.
    - Returns ``None`` if ``query`` is not a subsequence of ``candidate`` or if
      ``query`` is longer than ``candidate``.
    """
    if not query:
        return 0
    if len(query) > len(candidate):
        return None
    q = query.lower()
    c = candidate.lower()
    if c.startswith(q):
        return -len(q)

    score = 0
    last_pos = -1
    first_pos = -1
    qi = 0
    for i, ch in enumerate(c):
        if qi < len(q) and ch == q[qi]:
            if first_pos < 0:
                first_pos = i
            if last_pos >= 0:
                score += i - last_pos - 1
            last_pos = i
            qi += 1
    if qi != len(q):
        return None
    return score + first_pos


@dataclass(frozen=True)
class CompletionState:
    """Immutable snapshot of an in-progress completion."""

    matches: tuple[str, ...] = ()
    index: int = 0
    range_prefix: str = ""
    typed_command: str = ""


class CommandCompleter:
    """Tab-completion engine for ``:`` command mode."""

    def __init__(self, registry: CommandRegistry) -> None:
        self._registry = registry

    def complete(self, text: str) -> CompletionState:
        """Build a completion state for the given command-line text."""
        if not text:
            return CompletionState()

        match = _RANGE_PATTERN.match(text)
        range_prefix = match.group(1) if match else ""
        typed = match.group(2) if match else text

        if not typed:
            return CompletionState(range_prefix=range_prefix, typed_command="")

        names = self._registry.get_completions("")
        scored: list[tuple[int, str]] = []
        for name in names:
            score = fuzzy_score(typed, name)
            if score is not None:
                scored.append((score, name))
        scored.sort()
        matches = tuple(name for _, name in scored)

        return CompletionState(
            matches=matches,
            index=0,
            range_prefix=range_prefix,
            typed_command=typed,
        )

    @staticmethod
    def cycle_next(state: CompletionState) -> CompletionState:
        if not state.matches:
            return state
        return CompletionState(
            matches=state.matches,
            index=(state.index + 1) % len(state.matches),
            range_prefix=state.range_prefix,
            typed_command=state.typed_command,
        )

    @staticmethod
    def cycle_prev(state: CompletionState) -> CompletionState:
        if not state.matches:
            return state
        return CompletionState(
            matches=state.matches,
            index=(state.index - 1) % len(state.matches),
            range_prefix=state.range_prefix,
            typed_command=state.typed_command,
        )

    @staticmethod
    def current_ghost(state: CompletionState | None) -> str:
        if state is None or not state.matches:
            return ""
        return state.range_prefix + state.matches[state.index]

    @staticmethod
    def accept(state: CompletionState | None) -> str:
        if state is None or not state.matches:
            return ""
        return state.range_prefix + state.matches[state.index]

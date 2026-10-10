"""Fuzzy command-line completion for ex commands.

Splits a typed command into a vim-style range prefix (e.g. ``%``, ``5,10``,
``.``) and a typed command name, then ranks registered commands by a small
fuzzy score: prefix matches are preferred (negative scores), subsequence
matches fall back to a positive score based on character gaps and first-match
position. Cycling and ghost rendering operate on immutable :class:`CompletionState`
snapshots so the TUI layer stays stateless.

Once the command name is followed by a space, the last term of the
argument is completed instead, against candidates an ``arg_source``
supplies for the (alias-resolved) command. Matches are always whole
command lines, so ghosting, cycling, and accepting work the same for
names and arguments.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from vimtg.editor.commands import CommandRegistry

_RANGE_PATTERN = re.compile(r"^([^a-zA-Z_]*)(.*)$")
# The argument term being completed: after the last space, '+' or '|'
# (tag-filter operators), past any leading '-' / '#' / '@' sigils.
_ARG_TERM = re.compile(r"^(.*[\s+|])?([-#@]*)([^\s+|]*)$", re.DOTALL)

# Canonical command name -> argument candidates, in preference order
ArgSource = Callable[[str], Sequence[str]]


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

    def complete(
        self, text: str, arg_source: ArgSource | None = None,
    ) -> CompletionState:
        """Build a completion state for the given command-line text."""
        if not text:
            return CompletionState()

        match = _RANGE_PATTERN.match(text)
        range_prefix = match.group(1) if match else ""
        typed = match.group(2) if match else text

        if not typed:
            return CompletionState(range_prefix=range_prefix, typed_command="")

        command, space, arg = typed.partition(" ")
        if space:
            if arg_source is None:
                return CompletionState(range_prefix=range_prefix, typed_command=typed)
            return self._complete_argument(
                range_prefix, typed, command, arg, arg_source,
            )

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

    def _complete_argument(
        self, range_prefix: str, typed: str, command: str, arg: str,
        arg_source: ArgSource,
    ) -> CompletionState:
        """Complete the last term of `arg` for `command` (a trailing '!'
        is kept but ignored for lookup). Candidate order breaks ties."""
        candidates = arg_source(self._registry.resolve(command.rstrip("!")))
        term = _ARG_TERM.match(arg)
        if not candidates or term is None:
            return CompletionState(range_prefix=range_prefix, typed_command=typed)
        head = f"{command} {term.group(1) or ''}{term.group(2)}"
        word = term.group(3)
        scored: list[tuple[int, str]] = []
        for candidate in dict.fromkeys(candidates):
            score = fuzzy_score(word, candidate)
            if score is not None and candidate != word:
                scored.append((score, candidate))
        scored.sort(key=lambda pair: pair[0])  # stable: keeps source order
        return CompletionState(
            matches=tuple(head + candidate for _, candidate in scored),
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

"""Command-line history: Up/Down recall for `:` commands and searches.

Vim keeps one history per prompt kind; so does this. Entries are
de-duplicated (re-running a command moves it to the newest slot) and
capped. Up/Down recall entries that start with what was typed before
the first Up, as in vim. The histories persist as JSON in the XDG
state directory so they survive restarts; a missing or unreadable
file just means an empty history.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

HISTORY_LIMIT = 200
COMMAND = "cmd"
SEARCH = "search"
_KINDS = (COMMAND, SEARCH)


def history_path() -> Path:
    from vimtg.config.paths import state_dir

    return state_dir() / "cmdline_history.json"


class CommandHistory:
    """Per-kind entry lists plus the in-progress Up/Down browse."""

    def __init__(
        self, path: Path | None = None, limit: int = HISTORY_LIMIT
    ) -> None:
        self._path = path
        self._limit = limit
        self._entries: dict[str, list[str]] = {kind: [] for kind in _KINDS}
        # Browse state: index into the kind's entries (None = not
        # browsing) and the text typed before the first Up
        self._index: int | None = None
        self._typed = ""

    @classmethod
    def load(cls, path: Path | None = None) -> CommandHistory:
        """History from `path` (default: the state dir file)."""
        history = cls(path if path is not None else history_path())
        assert history._path is not None
        try:
            raw = json.loads(history._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return history
        if isinstance(raw, dict):
            for kind in _KINDS:
                items = raw.get(kind)
                if isinstance(items, list):
                    entries = [e for e in items if isinstance(e, str) and e]
                    history._entries[kind] = entries[-history._limit:]
        return history

    def entries(self, kind: str) -> tuple[str, ...]:
        return tuple(self._entries[kind])

    def add(self, kind: str, text: str) -> None:
        """Record a submitted line as the newest entry and persist."""
        self.reset_browse()
        if not text.strip():
            return
        entries = [e for e in self._entries[kind] if e != text]
        entries.append(text)
        self._entries[kind] = entries[-self._limit:]
        self._save()

    def reset_browse(self) -> None:
        self._index = None
        self._typed = ""

    def older(self, kind: str, current: str) -> str | None:
        """Up: the next older entry starting with the typed prefix, or
        None when there is none (the line stays as it is)."""
        if self._index is None:
            self._typed = current
            start = len(self._entries[kind])
        else:
            start = self._index
        for i in range(start - 1, -1, -1):
            if self._entries[kind][i].startswith(self._typed):
                self._index = i
                return self._entries[kind][i]
        return None

    def newer(self, kind: str) -> str | None:
        """Down: the next newer matching entry; past the newest, the
        text typed before browsing. None when not browsing."""
        if self._index is None:
            return None
        entries = self._entries[kind]
        for i in range(self._index + 1, len(entries)):
            if entries[i].startswith(self._typed):
                self._index = i
                return entries[i]
        typed = self._typed
        self.reset_browse()
        return typed

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._entries), encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError:
            pass  # history is a convenience; never fail a command over it

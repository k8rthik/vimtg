"""History service: the session undo stack for deck editing.

A linear list of snapshots with an index: `u` walks back, `Ctrl-R`
walks forward, and a new edit after an undo discards the entries past
the index. Quantity bursts fold into one step (see record).

Durable version control (snapshots and tags) is handled by
vimtg.services.vcs_service, not here.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from vimtg.editor.buffer import Buffer

# Only quantity bursts (+ + + / - - -) on the same lines fold into one
# undo step, like vim's insert-mode run. Operators, x, put and dot-repeat are always one
# change per u, so repeating one never swallows the step before it.
MERGEABLE_DESCRIPTIONS = frozenset({"increment", "decrement"})
MERGE_WINDOW_SECONDS = 2.0


@dataclass(frozen=True)
class Snapshot:
    """One undo step: the whole buffer text after a change."""

    id: int
    deck_state: str
    description: str


class HistoryService:
    """The session undo stack for deck edits."""

    def __init__(self) -> None:
        self._entries: list[Snapshot] = []
        self._index: int = -1
        self._next_id: int = 0
        self._last_record_time: float = 0
        self._last_description: str = ""
        # Id of the entry the last record() created or merged into. A
        # merge is only safe while that entry is still current: after u
        # or ctrl_r the current entry is an older state that must never
        # be rewritten.
        self._last_recorded_id: int | None = None
        self._last_rows: tuple[int, int] | None = None

    def _snapshot(self, text: str, description: str) -> Snapshot:
        snap = Snapshot(id=self._next_id, deck_state=text, description=description)
        self._next_id += 1
        return snap

    def initialize(self, buffer: Buffer) -> None:
        """Start a new stack holding only `buffer`."""
        self._entries = [self._snapshot(buffer.to_text(), "initial")]
        self._index = 0
        self._last_recorded_id = None

    def record(
        self, buffer: Buffer, description: str, rows: tuple[int, int] | None = None
    ) -> None:
        """Record a snapshot as the newest step, dropping any redo entries.

        A quantity change (see MERGEABLE_DESCRIPTIONS) within 2s of the
        same kind of change on the same `rows` folds into it — but only
        while that change is still the current entry, never after an
        undo or redo. `+ j +` stays two changes.
        """
        if not self._entries:
            self.initialize(buffer)
            return

        now = time.monotonic()
        if (
            description in MERGEABLE_DESCRIPTIONS
            and description == self._last_description
            and rows == self._last_rows
            and now - self._last_record_time < MERGE_WINDOW_SECONDS
            and self._last_recorded_id == self.current_id
        ):
            self.amend(buffer)
        else:
            del self._entries[self._index + 1:]
            self._entries.append(self._snapshot(buffer.to_text(), description))
            self._index += 1

        self._last_record_time = now
        self._last_description = description
        self._last_rows = rows
        self._last_recorded_id = self.current_id

    def amend(self, buffer: Buffer) -> None:
        """Replace the current snapshot's state without adding a new one.

        Used to fold follow-up normalization (e.g. section cleanup) into
        the edit that caused it, so it stays a single undo step. When
        that brings the text back to the previous state's, the edit
        changed nothing: its step is dropped, so u never undoes a no-op.
        """
        if not self._entries:
            self.initialize(buffer)
            return
        text = buffer.to_text()
        current = self._entries[self._index]
        is_newest = self._index == len(self._entries) - 1
        if self._index > 0 and is_newest and self._entries[self._index - 1].deck_state == text:
            self._entries.pop()
            self._index -= 1
            self._last_recorded_id = None
            return
        self._entries[self._index] = Snapshot(
            id=current.id, deck_state=text, description=current.description,
        )

    def undo(self) -> Buffer | None:
        """Step back once, returning the restored buffer or None at the start."""
        if self._index <= 0:
            return None
        self._index -= 1
        self._last_recorded_id = None  # the next edit is a new change
        return Buffer.from_text(self._entries[self._index].deck_state)

    def redo(self) -> Buffer | None:
        """Step forward once, returning the restored buffer or None at the end."""
        if self._index < 0 or self._index >= len(self._entries) - 1:
            return None
        self._index += 1
        self._last_recorded_id = None  # the next edit is a new change
        return Buffer.from_text(self._entries[self._index].deck_state)

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return 0 <= self._index < len(self._entries) - 1

    @property
    def current_id(self) -> int | None:
        """Id of the current entry (None before the first record). A
        caller keeps it to ask later whether its change is still the one
        on top, so a follow-up may fold into it."""
        return self._entries[self._index].id if self._entries else None

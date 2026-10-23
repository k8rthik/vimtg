"""History service managing the session undo tree for deck editing.

Provides undo/redo and debounced recording. Wraps SnapshotTree with
mutable state tracking (last record time, etc.) while keeping
SnapshotTree itself immutable.

Durable version control (branches, tags, merges) is handled by
vimtg.services.vcs_service, not here.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import time

from vimtg.domain.snapshot import Snapshot, SnapshotTree
from vimtg.editor.buffer import Buffer

# Only quantity bursts (+ + + / - - -) fold into one undo step, like
# vim's insert-mode run. Operators, x, put and dot-repeat are always one
# change per u, so repeating one never swallows the step before it.
MERGEABLE_DESCRIPTIONS = frozenset({"increment", "decrement"})
MERGE_WINDOW_SECONDS = 2.0


class HistoryService:
    """Manages the session undo tree for deck edits."""

    def __init__(self) -> None:
        self._tree: SnapshotTree | None = None
        self._last_record_time: float = 0
        self._last_description: str = ""
        # Id of the node the last record() created or merged into. A
        # merge is only safe while that node is still current: after u
        # or ctrl_r the current node is an older state that must never
        # be rewritten.
        self._last_recorded_id: str | None = None

    def initialize(self, buffer: Buffer) -> None:
        """Create a new tree from the given buffer."""
        self._tree = SnapshotTree.new(buffer.to_text())
        self._last_recorded_id = None

    def record(self, buffer: Buffer, description: str) -> None:
        """Record a snapshot.

        A quantity change (see MERGEABLE_DESCRIPTIONS) within 2s of the
        same kind of change folds into it — but only while that change
        is still the current node, never after an undo or redo.
        """
        if self._tree is None:
            self.initialize(buffer)
            return

        now = time.monotonic()
        if (
            description in MERGEABLE_DESCRIPTIONS
            and description == self._last_description
            and now - self._last_record_time < MERGE_WINDOW_SECONDS
            and self._last_recorded_id == self._tree.current_id
        ):
            self.amend(buffer)
        else:
            self._tree = self._tree.add_snapshot(buffer.to_text(), description)

        self._last_record_time = now
        self._last_description = description
        self._last_recorded_id = self._tree.current_id

    def amend(self, buffer: Buffer) -> None:
        """Replace the current snapshot's state without adding a new one.

        Used to fold follow-up normalization (e.g. section cleanup) into
        the edit that caused it, so it stays a single undo step. When
        that brings the text back to the parent's, the edit changed
        nothing: its step is dropped, so u never undoes a no-op.
        """
        if self._tree is None:
            self.initialize(buffer)
            return
        current = self._tree.current
        parent = self._tree.parent()
        text = buffer.to_text()
        if parent is not None and parent.deck_state == text and not self._tree.children():
            nodes = {k: v for k, v in self._tree.nodes.items() if k != current.id}
            self._tree = SnapshotTree(nodes=nodes, current_id=parent.id)
            self._last_recorded_id = None
            return
        updated = Snapshot(
            id=current.id,
            parent_id=current.parent_id,
            deck_state=text,
            timestamp=current.timestamp,
            description=current.description,
        )
        self._tree = SnapshotTree(
            nodes={**self._tree.nodes, updated.id: updated},
            current_id=self._tree.current_id,
        )

    def undo(self) -> Buffer | None:
        """Undo to parent snapshot, returning the restored buffer or None."""
        if self._tree is None:
            return None
        new_tree = self._tree.undo()
        if new_tree is None:
            return None
        self._tree = new_tree
        self._last_recorded_id = None  # the next edit is a new change
        return Buffer.from_text(self._tree.current.deck_state)

    def redo(self) -> Buffer | None:
        """Redo to most recent child, returning the restored buffer or None."""
        if self._tree is None:
            return None
        new_tree = self._tree.redo()
        if new_tree is None:
            return None
        self._tree = new_tree
        self._last_recorded_id = None  # the next edit is a new change
        return Buffer.from_text(self._tree.current.deck_state)

    @property
    def can_undo(self) -> bool:
        return self._tree is not None and self._tree.parent() is not None

    @property
    def can_redo(self) -> bool:
        return self._tree is not None and len(self._tree.children()) > 0

    @property
    def tree(self) -> SnapshotTree | None:
        return self._tree

    @property
    def current_id(self) -> str | None:
        """Id of the current node (None before the first record)."""
        return self._tree.current_id if self._tree is not None else None

"""History service managing a snapshot undo tree for deck editing.

Provides undo/redo, branching, checkpoints, and debounced recording.
Wraps SnapshotTree with mutable state tracking (last record time, etc.)
while keeping SnapshotTree itself immutable.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import time

from vimtg.domain.snapshot import Snapshot, SnapshotTree
from vimtg.editor.buffer import Buffer


class HistoryService:
    """Manages deck edit history with undo tree, branches, and checkpoints."""

    def __init__(self) -> None:
        self._tree: SnapshotTree | None = None
        self._last_record_time: float = 0
        self._last_description: str = ""

    def initialize(self, buffer: Buffer) -> None:
        """Create a new tree from the given buffer."""
        self._tree = SnapshotTree.new(buffer.to_text())

    def record(self, buffer: Buffer, description: str) -> None:
        """Record a snapshot. Debounces same-description records within 2s."""
        if self._tree is None:
            self.initialize(buffer)
            return

        now = time.monotonic()
        if now - self._last_record_time < 2.0 and description == self._last_description:
            # Coalesce: replace current snapshot's deck_state
            current = self._tree.current
            updated = Snapshot(
                id=current.id,
                parent_id=current.parent_id,
                deck_state=buffer.to_text(),
                timestamp=current.timestamp,
                description=description,
                branch=current.branch,
                tag=current.tag,
            )
            new_nodes = {**self._tree.nodes, updated.id: updated}
            self._tree = SnapshotTree(
                nodes=new_nodes,
                current_id=self._tree.current_id,
                branches=self._tree.branches,
            )
        else:
            self._tree = self._tree.add_snapshot(buffer.to_text(), description)

        self._last_record_time = now
        self._last_description = description

    def undo(self) -> Buffer | None:
        """Undo to parent snapshot, returning the restored buffer or None."""
        if self._tree is None:
            return None
        new_tree = self._tree.undo()
        if new_tree is None:
            return None
        self._tree = new_tree
        return Buffer.from_text(self._tree.current.deck_state)

    def redo(self) -> Buffer | None:
        """Redo to most recent child, returning the restored buffer or None."""
        if self._tree is None:
            return None
        new_tree = self._tree.redo()
        if new_tree is None:
            return None
        self._tree = new_tree
        return Buffer.from_text(self._tree.current.deck_state)

    def checkpoint(self, name: str) -> None:
        """Tag the current snapshot with a checkpoint name."""
        if self._tree is not None:
            self._tree = self._tree.checkpoint(name)

    def create_branch(self, name: str) -> None:
        """Create a new branch at the current snapshot."""
        if self._tree is not None:
            self._tree = self._tree.create_branch(name)

    def switch_branch(self, name: str) -> Buffer | None:
        """Switch to a branch tip, returning the restored buffer or None."""
        if self._tree is None:
            return None
        new_tree = self._tree.switch_branch(name)
        if new_tree is None:
            return None
        self._tree = new_tree
        return Buffer.from_text(self._tree.current.deck_state)

    def list_branches(self) -> list[str]:
        """Return names of all branches."""
        if self._tree is None:
            return []
        return list(self._tree.branches.keys())

    @property
    def can_undo(self) -> bool:
        return self._tree is not None and self._tree.parent() is not None

    @property
    def can_redo(self) -> bool:
        return self._tree is not None and len(self._tree.children()) > 0

    @property
    def tree(self) -> SnapshotTree | None:
        return self._tree

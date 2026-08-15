"""Snapshot-based session undo tree.

Each snapshot captures the full deck state at a point in time.
Snapshots form a tree: undo/redo navigate linearly, and diverging
edits after an undo create forks (redo picks the newest child).

This is the in-memory, per-session undo model. Durable version
control (branches, tags, merges) lives in vimtg.domain.vcs.

All mutations return new SnapshotTree instances -- the original is never modified.
TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Snapshot:
    """A single point-in-time capture of deck state."""

    id: str
    parent_id: str | None
    deck_state: str  # serialized buffer text
    timestamp: datetime
    description: str


@dataclass(frozen=True)
class SnapshotTree:
    """Immutable tree of snapshots supporting undo and redo."""

    nodes: dict[str, Snapshot]
    current_id: str

    @property
    def current(self) -> Snapshot:
        return self.nodes[self.current_id]

    def parent(self) -> Snapshot | None:
        pid = self.current.parent_id
        return self.nodes.get(pid) if pid else None

    def children(self) -> list[Snapshot]:
        return sorted(
            [s for s in self.nodes.values() if s.parent_id == self.current_id],
            key=lambda s: s.timestamp,
            reverse=True,
        )

    def undo(self) -> SnapshotTree | None:
        """Move to parent snapshot, or None if at root."""
        parent = self.parent()
        if parent is None:
            return None
        return SnapshotTree(nodes=self.nodes, current_id=parent.id)

    def redo(self) -> SnapshotTree | None:
        """Move to most recent child snapshot, or None if at leaf."""
        kids = self.children()
        if not kids:
            return None
        return SnapshotTree(nodes=self.nodes, current_id=kids[0].id)

    def add_snapshot(self, deck_state: str, description: str) -> SnapshotTree:
        """Create a new snapshot as child of current, and advance to it."""
        snap = Snapshot(
            id=str(uuid.uuid4()),
            parent_id=self.current_id,
            deck_state=deck_state,
            timestamp=datetime.now(UTC),
            description=description,
        )
        return SnapshotTree(
            nodes={**self.nodes, snap.id: snap}, current_id=snap.id
        )

    @staticmethod
    def new(initial_state: str) -> SnapshotTree:
        """Create a fresh tree with a single root snapshot."""
        snap = Snapshot(
            id=str(uuid.uuid4()),
            parent_id=None,
            deck_state=initial_state,
            timestamp=datetime.now(UTC),
            description="initial",
        )
        return SnapshotTree(nodes={snap.id: snap}, current_id=snap.id)

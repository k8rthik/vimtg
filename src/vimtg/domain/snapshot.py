"""Snapshot-based undo tree with branches and checkpoints.

Each snapshot captures the full deck state at a point in time.
Snapshots form a tree: undo/redo navigate linearly, while branches
allow diverging edit histories. Checkpoints tag a snapshot with a name.

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
    branch: str = "main"
    tag: str | None = None


@dataclass(frozen=True)
class SnapshotTree:
    """Immutable tree of snapshots supporting undo, redo, branches, and checkpoints."""

    nodes: dict[str, Snapshot]
    current_id: str
    branches: dict[str, str]  # branch_name -> tip_snapshot_id

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
        return SnapshotTree(
            nodes=self.nodes, current_id=parent.id, branches=self.branches
        )

    def redo(self) -> SnapshotTree | None:
        """Move to most recent child snapshot, or None if at leaf."""
        kids = self.children()
        if not kids:
            return None
        return SnapshotTree(
            nodes=self.nodes, current_id=kids[0].id, branches=self.branches
        )

    def add_snapshot(self, deck_state: str, description: str) -> SnapshotTree:
        """Create a new snapshot as child of current, and advance to it."""
        snap = Snapshot(
            id=str(uuid.uuid4()),
            parent_id=self.current_id,
            deck_state=deck_state,
            timestamp=datetime.now(UTC),
            description=description,
            branch=self.current.branch,
        )
        new_nodes = {**self.nodes, snap.id: snap}
        new_branches = {**self.branches, snap.branch: snap.id}
        return SnapshotTree(
            nodes=new_nodes, current_id=snap.id, branches=new_branches
        )

    def checkpoint(self, name: str) -> SnapshotTree:
        """Tag the current snapshot with a checkpoint name."""
        current = self.current
        tagged = Snapshot(
            id=current.id,
            parent_id=current.parent_id,
            deck_state=current.deck_state,
            timestamp=current.timestamp,
            description=current.description,
            branch=current.branch,
            tag=name,
        )
        new_nodes = {**self.nodes, tagged.id: tagged}
        return SnapshotTree(
            nodes=new_nodes, current_id=self.current_id, branches=self.branches
        )

    def create_branch(self, name: str) -> SnapshotTree:
        """Create a new branch pointing at the current snapshot."""
        new_branches = {**self.branches, name: self.current_id}
        return SnapshotTree(
            nodes=self.nodes, current_id=self.current_id, branches=new_branches
        )

    def switch_branch(self, name: str) -> SnapshotTree | None:
        """Switch to the tip of the named branch, or None if unknown."""
        tip_id = self.branches.get(name)
        if tip_id is None or tip_id not in self.nodes:
            return None
        return SnapshotTree(
            nodes=self.nodes, current_id=tip_id, branches=self.branches
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
            branch="main",
        )
        return SnapshotTree(
            nodes={snap.id: snap},
            current_id=snap.id,
            branches={"main": snap.id},
        )

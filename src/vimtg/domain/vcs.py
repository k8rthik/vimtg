"""Persistent version control dataclasses for deck history.

Separate from the in-memory SnapshotTree used for session undo/redo.
These types represent SQLite-persisted snapshots that survive across
editing sessions.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VCSSnapshot:
    """A persisted point-in-time deck state (like a git commit)."""

    id: str
    deck_path: str
    parent_id: str | None
    deck_state: str
    timestamp: datetime
    description: str
    tag: str | None = None
    deck_hash: str = ""


@dataclass(frozen=True)
class VCSStatus:
    """Current VCS state for a deck (displayed in status line)."""

    snapshot_count: int
    has_uncommitted_changes: bool
    last_snapshot_description: str = ""

"""Persistent version control service for deck history.

One linear chain of snapshots per deck path: commit, tag, restore.
Separate from the in-memory HistoryService used for session undo/redo.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import replace
from datetime import UTC, datetime

from vimtg.data.deck_repository import parse_deck_text
from vimtg.data.snapshot_repository import SnapshotRepository
from vimtg.domain.deck import DeckEntry
from vimtg.domain.sideboard_plan import SideboardPlan
from vimtg.domain.vcs import VCSSnapshot, VCSStatus


def _deck_hash(deck_state: str) -> str:
    """SHA-256 hash of deck state for dedup."""
    return hashlib.sha256(deck_state.encode("utf-8")).hexdigest()[:16]


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


def _semantic_entries(
    entries: tuple[DeckEntry, ...],
) -> tuple[tuple[object, ...], ...]:
    """Deck entries with buffer positions normalized out.

    line_number shifts whenever unrelated lines (e.g. scaffolded metadata)
    move an entry, and must not count as a deck change.
    """
    return tuple(
        (e.quantity, e.card_name, e.section, e.tags, e.comment)
        for e in entries
    )


def _semantic_plans(
    plans: tuple[SideboardPlan, ...],
) -> tuple[tuple[object, ...], ...]:
    """Sideboard plans with buffer positions normalized out."""
    return tuple(
        (
            p.name,
            p.note,
            tuple((e.sign, e.quantity, e.card_name, e.comment) for e in p.entries),
        )
        for p in plans
    )


class VersionControlService:
    """Persistent version control for deck history."""

    def __init__(
        self,
        snapshot_repo: SnapshotRepository,
        deck_path: str,
    ) -> None:
        self._repo = snapshot_repo
        self._deck_path = deck_path

    @property
    def deck_path(self) -> str:
        return self._deck_path

    def _tip(self) -> VCSSnapshot | None:
        return self._repo.tip(self._deck_path)

    # ── Core operations ───────────────────────────────────

    def commit(self, deck_state: str, description: str) -> VCSSnapshot:
        """Append a snapshot to the deck's history."""
        tip = self._tip()
        if tip is not None and tip.deck_hash == _deck_hash(deck_state):
            if _is_auto(tip.description) and not _is_auto(description):
                # :w snapshots on save; a :commit of that same deck names
                # the snapshot instead of losing its message
                self._repo.update_snapshot_description(tip.id, description)
                return replace(tip, description=description)
            return tip

        snap = VCSSnapshot(
            id=_new_id(),
            deck_path=self._deck_path,
            parent_id=tip.id if tip is not None else None,
            deck_state=deck_state,
            timestamp=_now(),
            description=description,
            deck_hash=_deck_hash(deck_state),
        )
        self._repo.save_snapshot(snap)
        return snap

    def get_log(self, limit: int = 50) -> list[VCSSnapshot]:
        """Snapshot history, newest first."""
        tip = self._tip()
        if tip is None:
            return []
        return self._repo.get_ancestors(tip.id, limit=limit)

    def checkout(self, snapshot_id: str) -> str | None:
        """Return deck_state for a snapshot (read-only)."""
        snap = self._repo.get_snapshot(snapshot_id)
        return snap.deck_state if snap else None

    def restore(self, snapshot_id: str) -> VCSSnapshot | None:
        """Create a new commit with the state from an old snapshot."""
        old_snap = self._repo.get_snapshot(snapshot_id)
        if old_snap is None:
            return None
        return self.commit(
            old_snap.deck_state,
            f"restore: {old_snap.description}",
        )

    # ── Tag operations ────────────────────────────────────

    def tag(self, snapshot_id: str, tag_name: str) -> bool:
        """Tag a snapshot. Returns False if snapshot not found."""
        snap = self._repo.get_snapshot(snapshot_id)
        if snap is None:
            return False
        self._repo.update_snapshot_tag(snapshot_id, tag_name)
        return True

    def untag(self, snapshot_id: str) -> bool:
        """Remove tag from a snapshot."""
        snap = self._repo.get_snapshot(snapshot_id)
        if snap is None:
            return False
        self._repo.update_snapshot_tag(snapshot_id, None)
        return True

    # ── Working copy ──────────────────────────────────────

    def is_dirty(self, current_deck_state: str) -> bool:
        """True if the working state meaningfully differs from the tip.

        A deck with no commits yet is considered dirty (nothing recorded).
        When the raw text differs, fall back to comparing parsed cards and
        metadata — opening a deck scaffolds missing metadata lines into
        the buffer, and that cosmetic drift must not show as uncommitted
        changes.
        """
        tip = self._tip()
        if tip is None:
            return True
        if _deck_hash(current_deck_state) == tip.deck_hash:
            return False
        tip_deck = parse_deck_text(tip.deck_state)
        current_deck = parse_deck_text(current_deck_state)
        return (
            _semantic_entries(tip_deck.entries)
            != _semantic_entries(current_deck.entries)
            or tip_deck.metadata != current_deck.metadata
            or _semantic_plans(tip_deck.plans) != _semantic_plans(current_deck.plans)
        )

    def status(self, current_deck_state: str) -> VCSStatus:
        """Get current VCS status for status line display."""
        tip = self._tip()
        return VCSStatus(
            snapshot_count=self._repo.snapshot_count(self._deck_path),
            has_uncommitted_changes=(
                tip is None or _deck_hash(current_deck_state) != tip.deck_hash
            ),
            last_snapshot_description=tip.description if tip is not None else "",
        )


AUTO_PREFIX = "auto:"


def _is_auto(description: str) -> bool:
    return description.startswith(AUTO_PREFIX)


def commit_message(snap: VCSSnapshot, requested: str) -> str:
    """What a commit reports: the snapshot it made, or that nothing changed."""
    if snap.description == requested:
        return f"Snapshot: {snap.description}"
    return f"Nothing to commit: the deck matches snapshot '{snap.description}'"

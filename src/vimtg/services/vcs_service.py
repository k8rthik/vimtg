"""Persistent version control service for deck history.

Manages snapshots, branches, tags, and advanced operations (restore,
cherry-pick, squash, merge). Separate from the in-memory HistoryService
used for session undo/redo.

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
from vimtg.domain.deck_diff import DeckDiff, compute_deck_diff
from vimtg.domain.vcs import VCSBranch, VCSSnapshot, VCSStatus


def _deck_hash(deck_state: str) -> str:
    """SHA-256 hash of deck state for dedup."""
    return hashlib.sha256(deck_state.encode("utf-8")).hexdigest()[:16]


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class VersionControlService:
    """Persistent version control for deck history."""

    def __init__(
        self,
        snapshot_repo: SnapshotRepository,
        deck_path: str,
    ) -> None:
        self._repo = snapshot_repo
        self._deck_path = deck_path
        self._current_branch: str = "main"

    @property
    def current_branch(self) -> str:
        return self._current_branch

    @property
    def deck_path(self) -> str:
        return self._deck_path

    # ── Core operations ───────────────────────────────────

    def commit(self, deck_state: str, description: str) -> VCSSnapshot:
        """Create a new snapshot on the current branch."""
        # Find parent (current branch tip)
        branch = self._repo.get_branch(self._deck_path, self._current_branch)
        parent_id = branch.tip_id if branch else None

        # Dedup check: skip if hash matches parent
        if parent_id:
            parent = self._repo.get_snapshot(parent_id)
            if parent and parent.deck_hash == _deck_hash(deck_state):
                return parent

        snap = VCSSnapshot(
            id=_new_id(),
            deck_path=self._deck_path,
            parent_id=parent_id,
            deck_state=deck_state,
            timestamp=_now(),
            description=description,
            branch=self._current_branch,
            deck_hash=_deck_hash(deck_state),
        )
        self._repo.save_snapshot(snap)

        # Update or create branch tip
        if branch:
            self._repo.update_branch_tip(
                self._deck_path, self._current_branch, snap.id,
            )
        else:
            self._repo.save_branch(VCSBranch(
                name=self._current_branch,
                deck_path=self._deck_path,
                tip_id=snap.id,
                created_at=_now(),
            ))

        return snap

    def get_log(
        self, branch: str | None = None, limit: int = 50
    ) -> list[VCSSnapshot]:
        """Get snapshot history for current/specified branch."""
        target = branch or self._current_branch
        branch_obj = self._repo.get_branch(self._deck_path, target)
        if branch_obj is None:
            return []
        return self._repo.get_ancestors(branch_obj.tip_id, limit=limit)

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

    # ── Branch operations ─────────────────────────────────

    def create_branch(self, name: str) -> VCSBranch | None:
        """Create a new branch at the current branch tip."""
        existing = self._repo.get_branch(self._deck_path, name)
        if existing is not None:
            return None  # Branch already exists

        current_branch = self._repo.get_branch(
            self._deck_path, self._current_branch,
        )
        tip_id = current_branch.tip_id if current_branch else None
        if tip_id is None:
            return None  # No snapshots yet

        branch = VCSBranch(
            name=name,
            deck_path=self._deck_path,
            tip_id=tip_id,
            created_at=_now(),
        )
        self._repo.save_branch(branch)
        return branch

    def switch_branch(self, name: str) -> str | None:
        """Switch to a branch, return its tip deck_state."""
        branch = self._repo.get_branch(self._deck_path, name)
        if branch is None:
            return None
        self._current_branch = name
        tip = self._repo.get_snapshot(branch.tip_id)
        return tip.deck_state if tip else None

    def list_branches(self) -> list[VCSBranch]:
        """List all branches for this deck."""
        return self._repo.list_branches(self._deck_path)

    def delete_branch(self, name: str) -> bool:
        """Delete a branch (cannot delete current branch)."""
        if name == self._current_branch:
            return False
        existing = self._repo.get_branch(self._deck_path, name)
        if existing is None:
            return False
        self._repo.delete_branch(self._deck_path, name)
        return True

    def merge_branch(self, source_branch: str) -> DeckDiff | None:
        """Merge source branch tip into current branch.

        MTG merge strategy: take source branch state as the new state.
        Creates a new commit on current branch with the merged result.
        """
        source = self._repo.get_branch(self._deck_path, source_branch)
        if source is None:
            return None
        source_tip = self._repo.get_snapshot(source.tip_id)
        if source_tip is None:
            return None

        current = self._repo.get_branch(self._deck_path, self._current_branch)
        current_state = ""
        if current:
            current_tip = self._repo.get_snapshot(current.tip_id)
            current_state = current_tip.deck_state if current_tip else ""

        diff = compute_deck_diff(current_state, source_tip.deck_state)

        self.commit(
            source_tip.deck_state,
            f"merge: {source_branch} into {self._current_branch}",
        )
        return diff

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

    # ── Advanced operations ───────────────────────────────

    def cherry_pick(self, snapshot_id: str) -> DeckDiff | None:
        """Apply the diff from a single snapshot onto current branch.

        Computes what changed in the target snapshot vs its parent,
        then applies those card changes to the current branch tip.
        """
        snap = self._repo.get_snapshot(snapshot_id)
        if snap is None:
            return None

        # Get parent state
        parent_state = ""
        if snap.parent_id:
            parent = self._repo.get_snapshot(snap.parent_id)
            parent_state = parent.deck_state if parent else ""

        # Get current branch tip state
        current_branch = self._repo.get_branch(
            self._deck_path, self._current_branch,
        )
        if current_branch is None:
            return None
        current_tip = self._repo.get_snapshot(current_branch.tip_id)
        if current_tip is None:
            return None

        # Compute what the source snapshot changed
        source_diff = compute_deck_diff(parent_state, snap.deck_state)

        # Apply those changes to current state
        current_deck = parse_deck_text(current_tip.deck_state)
        result_entries = list(current_deck.entries)

        for change in source_diff.changes:
            if change.change_type.value == "added":
                # Add card if not already present
                existing = [
                    e for e in result_entries
                    if e.card_name == change.card_name
                    and e.section == change.section
                ]
                if not existing and change.new_quantity:
                    result_entries.append(DeckEntry(
                        quantity=change.new_quantity,
                        card_name=change.card_name,
                        section=change.section,
                    ))
            elif change.change_type.value == "removed":
                result_entries = [
                    e for e in result_entries
                    if not (
                        e.card_name == change.card_name
                        and e.section == change.section
                    )
                ]
            elif change.change_type.value == "quantity_changed":
                result_entries = [
                    replace(e, quantity=change.new_quantity)
                    if (
                        e.card_name == change.card_name
                        and e.section == change.section
                        and change.new_quantity is not None
                    )
                    else e
                    for e in result_entries
                ]

        # Serialize the result
        from vimtg.data.deck_repository import serialize_deck
        from vimtg.domain.deck import Deck

        result_deck = Deck(
            metadata=current_deck.metadata,
            entries=tuple(result_entries),
            comments=current_deck.comments,
        )
        new_state = serialize_deck(result_deck)

        diff = compute_deck_diff(current_tip.deck_state, new_state)
        self.commit(new_state, f"cherry-pick: {snap.description}")
        return diff

    def squash(
        self, snapshot_ids: list[str], description: str
    ) -> VCSSnapshot | None:
        """Combine multiple snapshots into one, keeping the final state.

        The snapshots must be consecutive on the current branch.
        Replaces them with a single snapshot.
        """
        if not snapshot_ids:
            return None

        # Get all snapshots and verify they exist
        snapshots = []
        for sid in snapshot_ids:
            snap = self._repo.get_snapshot(sid)
            if snap is None:
                return None
            snapshots.append(snap)

        # Use the last snapshot's state
        final_state = snapshots[-1].deck_state
        first_parent = snapshots[0].parent_id

        # Create replacement snapshot
        replacement = VCSSnapshot(
            id=_new_id(),
            deck_path=self._deck_path,
            parent_id=first_parent,
            deck_state=final_state,
            timestamp=_now(),
            description=description,
            branch=self._current_branch,
            deck_hash=_deck_hash(final_state),
        )
        self._repo.save_snapshot(replacement)

        # Update branch tip if it was pointing at one of the squashed
        branch = self._repo.get_branch(self._deck_path, self._current_branch)
        if branch and branch.tip_id in snapshot_ids:
            self._repo.update_branch_tip(
                self._deck_path, self._current_branch, replacement.id,
            )

        # Delete old snapshots
        self._repo.delete_snapshots_by_ids(snapshot_ids)

        return replacement

    # ── Status ────────────────────────────────────────────

    def status(self, current_deck_state: str) -> VCSStatus:
        """Get current VCS status for status line display."""
        count = self._repo.snapshot_count(self._deck_path)

        branch = self._repo.get_branch(self._deck_path, self._current_branch)
        last_desc = ""
        has_changes = True

        if branch:
            tip = self._repo.get_snapshot(branch.tip_id)
            if tip:
                last_desc = tip.description
                has_changes = _deck_hash(current_deck_state) != tip.deck_hash

        return VCSStatus(
            branch=self._current_branch,
            snapshot_count=count,
            has_uncommitted_changes=has_changes,
            last_snapshot_description=last_desc,
        )

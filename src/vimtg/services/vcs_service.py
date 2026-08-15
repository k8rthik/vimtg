"""Persistent version control service for deck history.

Manages snapshots, branches, tags, and advanced operations (restore,
cherry-pick, squash, merge, rebase). Separate from the in-memory
HistoryService used for session undo/redo.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from vimtg.data.deck_repository import parse_deck_text
from vimtg.data.snapshot_repository import SnapshotRepository
from vimtg.domain.deck import DeckEntry
from vimtg.domain.deck_diff import DeckDiff, compute_deck_diff
from vimtg.domain.deck_merge import (
    CardKey,
    MergeConflict,
    apply_card_changes,
    merged_map_to_deck_state,
    three_way_merge,
)
from vimtg.domain.vcs import VCSBranch, VCSSnapshot, VCSStatus


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


class MergeKind(Enum):
    """Outcome classification for merge and rebase operations."""

    UP_TO_DATE = "up_to_date"
    FAST_FORWARD = "fast_forward"
    MERGED = "merged"
    CONFLICTS = "conflicts"
    FAILED = "failed"


@dataclass(frozen=True)
class PendingMerge:
    """A merge paused on conflicts, awaiting per-card resolutions.

    Nothing is committed until complete_merge — aborting a pending merge
    requires no cleanup. theirs_tip_id is None for external (cross-deck)
    merges, whose source is file content rather than a snapshot.
    """

    source_label: str
    ours_tip_id: str
    theirs_tip_id: str | None
    ours_state: str
    merged: dict[CardKey, int]
    conflicts: tuple[MergeConflict, ...]


@dataclass(frozen=True)
class MergeResult:
    """Outcome of a merge attempt."""

    kind: MergeKind
    message: str
    new_state: str | None = None
    snapshot: VCSSnapshot | None = None
    pending: PendingMerge | None = None


@dataclass(frozen=True)
class RebaseResult:
    """Outcome of a rebase attempt."""

    kind: MergeKind
    message: str
    new_state: str | None = None
    replayed: int = 0
    skipped: int = 0


class VersionControlService:
    """Persistent version control for deck history."""

    def __init__(
        self,
        snapshot_repo: SnapshotRepository,
        deck_path: str,
    ) -> None:
        self._repo = snapshot_repo
        self._deck_path = deck_path
        self._current_branch = self._restore_head()

    def _restore_head(self) -> str:
        """Load the persisted current branch, falling back to main.

        A stale head (naming a branch that no longer exists) falls back
        to main rather than resurrecting the missing branch.
        """
        head = self._repo.get_head(self._deck_path)
        if head is None or head == "main":
            return "main"
        if self._repo.get_branch(self._deck_path, head) is None:
            return "main"
        return head

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
        self._repo.set_head(self._deck_path, name)
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

    def merge_branch(self, source_branch: str) -> MergeResult:
        """Merge source branch tip into the current branch.

        Fast-forwards when possible (moving the ref, no commit); otherwise
        performs a 3-way card-level merge against the common ancestor.
        Conflicts return a PendingMerge for interactive resolution —
        nothing is committed until complete_merge.
        """
        source = self._repo.get_branch(self._deck_path, source_branch)
        if source is None:
            return MergeResult(
                MergeKind.FAILED, f"Branch not found: {source_branch}"
            )
        source_tip = self._repo.get_snapshot(source.tip_id)
        if source_tip is None:
            return MergeResult(
                MergeKind.FAILED, f"Branch tip missing: {source_branch}"
            )

        current = self._repo.get_branch(self._deck_path, self._current_branch)
        if current is None:
            # Unborn current branch: adopt the source tip wholesale.
            self._repo.save_branch(VCSBranch(
                name=self._current_branch,
                deck_path=self._deck_path,
                tip_id=source.tip_id,
                created_at=_now(),
            ))
            return MergeResult(
                MergeKind.FAST_FORWARD,
                f"Fast-forward: {self._current_branch} → {source_branch}",
                new_state=source_tip.deck_state,
            )

        if source_branch == self._current_branch or self._repo.is_ancestor(
            source.tip_id, current.tip_id, self._deck_path
        ):
            return MergeResult(MergeKind.UP_TO_DATE, "Already up to date")

        if self._repo.is_ancestor(
            current.tip_id, source.tip_id, self._deck_path
        ):
            self._repo.update_branch_tip(
                self._deck_path, self._current_branch, source.tip_id
            )
            return MergeResult(
                MergeKind.FAST_FORWARD,
                f"Fast-forward: {self._current_branch} → {source_branch}",
                new_state=source_tip.deck_state,
            )

        current_tip = self._repo.get_snapshot(current.tip_id)
        if current_tip is None:
            return MergeResult(MergeKind.FAILED, "Current branch tip missing")

        base_state = ""
        base_id = self._repo.find_merge_base(
            current.tip_id, source.tip_id, self._deck_path
        )
        if base_id is not None:
            base = self._repo.get_snapshot(base_id)
            base_state = base.deck_state if base else ""

        result = three_way_merge(
            base_state, current_tip.deck_state, source_tip.deck_state
        )
        if result.has_conflicts:
            return MergeResult(
                MergeKind.CONFLICTS,
                f"{len(result.conflicts)} conflict(s) — resolve to merge",
                pending=PendingMerge(
                    source_label=source_branch,
                    ours_tip_id=current.tip_id,
                    theirs_tip_id=source.tip_id,
                    ours_state=current_tip.deck_state,
                    merged=result.merged,
                    conflicts=result.conflicts,
                ),
            )

        new_state = merged_map_to_deck_state(
            result.merged, current_tip.deck_state
        )
        snap = self._commit_merge(
            new_state,
            f"merge: {source_branch} into {self._current_branch}",
            source.tip_id,
        )
        return MergeResult(
            MergeKind.MERGED,
            f"Merged {source_branch} into {self._current_branch}",
            new_state=new_state,
            snapshot=snap,
        )

    def merge_external(self, theirs_state: str, label: str) -> MergeResult:
        """Merge an external deck state (another deck file) into this one.

        Unrelated histories: the merge base is the empty deck, so their
        cards are additions and conflicts arise only where both decks hold
        the same card at different quantities. The resulting commit has no
        second parent — the source is file content, not a snapshot.
        """
        current = self._repo.get_branch(self._deck_path, self._current_branch)
        ours_tip_id = ""
        ours_state = ""
        if current is not None:
            tip = self._repo.get_snapshot(current.tip_id)
            if tip is not None:
                ours_tip_id = tip.id
                ours_state = tip.deck_state

        if ours_state and _deck_hash(theirs_state) == _deck_hash(ours_state):
            return MergeResult(
                MergeKind.UP_TO_DATE, "Already identical — nothing to merge"
            )

        result = three_way_merge("", ours_state, theirs_state)
        if result.has_conflicts:
            return MergeResult(
                MergeKind.CONFLICTS,
                f"{len(result.conflicts)} conflict(s) — resolve to merge",
                pending=PendingMerge(
                    source_label=label,
                    ours_tip_id=ours_tip_id,
                    theirs_tip_id=None,
                    ours_state=ours_state,
                    merged=result.merged,
                    conflicts=result.conflicts,
                ),
            )

        new_state = merged_map_to_deck_state(result.merged, ours_state)
        if ours_state and _deck_hash(new_state) == _deck_hash(ours_state):
            return MergeResult(
                MergeKind.UP_TO_DATE, "Nothing to merge — no new cards"
            )
        snap = self.commit(new_state, f"merge deck: {label}")
        return MergeResult(
            MergeKind.MERGED,
            f"Merged deck {label} into {self._current_branch}",
            new_state=new_state,
            snapshot=snap,
        )

    def complete_merge(
        self,
        pending: PendingMerge,
        resolutions: dict[CardKey, int | None],
    ) -> MergeResult:
        """Finish a conflicted merge with per-card resolutions.

        Every conflict key must appear in resolutions; None omits the card
        from the merged deck.
        """
        missing = [
            c.key for c in pending.conflicts if c.key not in resolutions
        ]
        if missing:
            return MergeResult(
                MergeKind.FAILED,
                f"{len(missing)} conflict(s) unresolved",
                pending=pending,
            )

        merged = dict(pending.merged)
        for conflict in pending.conflicts:
            resolved = resolutions[conflict.key]
            if resolved is not None:
                merged[conflict.key] = resolved

        new_state = merged_map_to_deck_state(merged, pending.ours_state)
        snap = self._commit_merge(
            new_state,
            f"merge: {pending.source_label} into {self._current_branch}",
            pending.theirs_tip_id,
        )
        return MergeResult(
            MergeKind.MERGED,
            f"Merged {pending.source_label} into {self._current_branch}",
            new_state=new_state,
            snapshot=snap,
        )

    def _commit_merge(
        self,
        deck_state: str,
        description: str,
        merge_parent_id: str | None,
    ) -> VCSSnapshot:
        """Create a merge commit on the current branch.

        Unlike commit(), skips hash dedup — a merge whose tree equals the
        current tip must still be recorded so ancestry is captured (the
        true no-op case is caught earlier as UP_TO_DATE).
        """
        branch = self._repo.get_branch(self._deck_path, self._current_branch)
        parent_id = branch.tip_id if branch else None

        snap = VCSSnapshot(
            id=_new_id(),
            deck_path=self._deck_path,
            parent_id=parent_id,
            deck_state=deck_state,
            timestamp=_now(),
            description=description,
            branch=self._current_branch,
            deck_hash=_deck_hash(deck_state),
            merge_parent_id=merge_parent_id,
        )
        self._repo.save_snapshot(snap)

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

    def rebase(self, target_branch: str) -> RebaseResult:
        """Replay the current branch's commits onto the target branch tip.

        Commits between the merge base and the current tip are collected
        via a first-parent walk (in-range merge commits linearize to their
        first-parent diff) and replayed oldest-first. Overlapping edits
        resolve in favor of the replayed change; replays that become
        no-ops are skipped. Original snapshots are left orphaned in the
        database, recoverable by id.
        """
        target = self._repo.get_branch(self._deck_path, target_branch)
        if target is None:
            return RebaseResult(
                MergeKind.FAILED, f"Branch not found: {target_branch}"
            )
        target_tip = self._repo.get_snapshot(target.tip_id)
        if target_tip is None:
            return RebaseResult(
                MergeKind.FAILED, f"Branch tip missing: {target_branch}"
            )
        current = self._repo.get_branch(self._deck_path, self._current_branch)
        if current is None:
            return RebaseResult(
                MergeKind.FAILED, "Nothing committed on the current branch"
            )

        if self._repo.is_ancestor(
            target.tip_id, current.tip_id, self._deck_path
        ):
            return RebaseResult(MergeKind.UP_TO_DATE, "Already up to date")

        if self._repo.is_ancestor(
            current.tip_id, target.tip_id, self._deck_path
        ):
            self._repo.update_branch_tip(
                self._deck_path, self._current_branch, target.tip_id
            )
            return RebaseResult(
                MergeKind.FAST_FORWARD,
                f"Fast-forward: {self._current_branch} → {target_branch}",
                new_state=target_tip.deck_state,
            )

        base_id = self._repo.find_merge_base(
            current.tip_id, target.tip_id, self._deck_path
        )

        # First-parent chain from current tip back to (exclusive of) base
        chain: list[VCSSnapshot] = []
        cursor = self._repo.get_snapshot(current.tip_id)
        while cursor is not None and cursor.id != base_id:
            chain.append(cursor)
            if cursor.parent_id is None:
                break
            cursor = self._repo.get_snapshot(cursor.parent_id)
        chain.reverse()

        state = target_tip.deck_state
        new_tip_id = target.tip_id
        replayed = 0
        skipped = 0
        for commit in chain:
            parent_state = ""
            if commit.parent_id:
                parent = self._repo.get_snapshot(commit.parent_id)
                parent_state = parent.deck_state if parent else ""
            diff = compute_deck_diff(parent_state, commit.deck_state)
            new_state = apply_card_changes(state, diff.changes)
            if _deck_hash(new_state) == _deck_hash(state):
                skipped += 1
                continue
            snap = VCSSnapshot(
                id=_new_id(),
                deck_path=self._deck_path,
                parent_id=new_tip_id,
                deck_state=new_state,
                timestamp=_now(),
                description=commit.description,
                branch=self._current_branch,
                deck_hash=_deck_hash(new_state),
            )
            self._repo.save_snapshot(snap)
            new_tip_id = snap.id
            state = new_state
            replayed += 1

        self._repo.update_branch_tip(
            self._deck_path, self._current_branch, new_tip_id
        )
        message = f"Rebased {replayed} commit(s) onto {target_branch}"
        if skipped:
            message += f" ({skipped} skipped as empty)"
        return RebaseResult(
            MergeKind.MERGED,
            message,
            new_state=state,
            replayed=replayed,
            skipped=skipped,
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

        # Compute what the source snapshot changed, replay onto current tip
        source_diff = compute_deck_diff(parent_state, snap.deck_state)
        new_state = apply_card_changes(
            current_tip.deck_state, source_diff.changes
        )

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
        branch = self._repo.get_branch(self._deck_path, self._current_branch)
        update_tip = branch is not None and branch.tip_id in snapshot_ids
        self._repo.replace_snapshots(snapshot_ids, replacement, update_tip)

        return replacement

    # ── Status ────────────────────────────────────────────

    def is_dirty(self, current_deck_state: str) -> bool:
        """True if the working state meaningfully differs from the tip.

        A deck with no commits yet is considered dirty (nothing recorded).
        When the raw text differs, fall back to comparing parsed cards and
        metadata — opening a deck scaffolds missing metadata lines into
        the buffer, and that cosmetic drift must not lock the user out of
        merge/rebase/switch with a spurious "uncommitted changes".
        """
        branch = self._repo.get_branch(self._deck_path, self._current_branch)
        if branch is None:
            return True
        tip = self._repo.get_snapshot(branch.tip_id)
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
        )

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

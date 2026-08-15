"""Persistent storage for deck version control snapshots and branches."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from vimtg.data.database import Database
from vimtg.domain.vcs import VCSBranch, VCSSnapshot


def _parse_timestamp(value: object) -> datetime:
    """Parse a stored ISO timestamp, tolerating malformed rows."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.min


def _row_to_snapshot(row: dict[str, Any]) -> VCSSnapshot:
    """Convert a SQLite Row to a VCSSnapshot."""
    return VCSSnapshot(
        id=row["id"],
        deck_path=row["deck_path"],
        parent_id=row["parent_id"],
        deck_state=row["deck_state"],
        timestamp=_parse_timestamp(row["timestamp"]),
        description=row["description"] or "",
        branch=row["branch"] or "main",
        tag=row["tag"],
        deck_hash=row["deck_hash"] or "",
        merge_parent_id=row["merge_parent_id"],
    )


def _row_to_branch(row: dict[str, Any]) -> VCSBranch:
    """Convert a SQLite Row to a VCSBranch."""
    return VCSBranch(
        name=row["name"],
        deck_path=row["deck_path"],
        tip_id=row["tip_id"],
        created_at=_parse_timestamp(row["created_at"]),
    )


class SnapshotRepository:
    """SQLite CRUD for persistent deck snapshots and branches."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save_snapshot(self, snapshot: VCSSnapshot) -> None:
        """Insert a snapshot row."""
        conn = self._db.connect()
        conn.execute(
            """INSERT INTO snapshots
               (id, deck_path, parent_id, deck_state, timestamp,
                description, branch, tag, deck_hash, merge_parent_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.id,
                snapshot.deck_path,
                snapshot.parent_id,
                snapshot.deck_state,
                snapshot.timestamp.isoformat(),
                snapshot.description,
                snapshot.branch,
                snapshot.tag,
                snapshot.deck_hash,
                snapshot.merge_parent_id,
            ),
        )
        conn.commit()

    def get_snapshot(self, snapshot_id: str) -> VCSSnapshot | None:
        """Fetch a single snapshot by ID."""
        conn = self._db.connect()
        row = conn.execute(
            "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_snapshot(row)

    def list_snapshots(
        self,
        deck_path: str,
        branch: str | None = None,
        limit: int = 100,
    ) -> list[VCSSnapshot]:
        """List snapshots for a deck, optionally filtered by branch, newest first."""
        conn = self._db.connect()
        if branch is not None:
            rows = conn.execute(
                """SELECT * FROM snapshots
                   WHERE deck_path = ? AND branch = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (deck_path, branch, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM snapshots
                   WHERE deck_path = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (deck_path, limit),
            ).fetchall()
        return [_row_to_snapshot(r) for r in rows]

    def get_ancestors(
        self, snapshot_id: str, limit: int = 50
    ) -> list[VCSSnapshot]:
        """Walk parent chain from a snapshot to build linear history."""
        result: list[VCSSnapshot] = []
        current_id: str | None = snapshot_id
        conn = self._db.connect()
        while current_id is not None and len(result) < limit:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE id = ?", (current_id,)
            ).fetchone()
            if row is None:
                break
            snap = _row_to_snapshot(row)
            result.append(snap)
            current_id = snap.parent_id
        return result

    def update_snapshot_tag(
        self, snapshot_id: str, tag: str | None
    ) -> None:
        """Set or clear a tag on a snapshot."""
        conn = self._db.connect()
        conn.execute(
            "UPDATE snapshots SET tag = ? WHERE id = ?",
            (tag, snapshot_id),
        )
        conn.commit()

    def snapshot_count(self, deck_path: str) -> int:
        """Count total snapshots for a deck."""
        conn = self._db.connect()
        row = conn.execute(
            "SELECT COUNT(*) FROM snapshots WHERE deck_path = ?",
            (deck_path,),
        ).fetchone()
        return row[0] if row else 0

    def delete_snapshots_by_ids(self, snapshot_ids: list[str]) -> None:
        """Delete snapshots by their IDs."""
        if not snapshot_ids:
            return
        conn = self._db.connect()
        placeholders = ",".join("?" for _ in snapshot_ids)
        conn.execute(
            f"DELETE FROM snapshots WHERE id IN ({placeholders})",  # noqa: S608
            snapshot_ids,
        )
        conn.commit()

    def replace_snapshots(
        self,
        snapshot_ids: list[str],
        replacement: VCSSnapshot,
        update_tip: bool,
    ) -> None:
        """Atomically replace a run of snapshots with a single one.

        Inserts the replacement, re-parents any surviving children of the
        replaced snapshots, optionally moves the branch tip, and deletes
        the originals — all in one transaction so a failure can't leave
        dangling parent references.
        """
        if not snapshot_ids:
            return
        conn = self._db.connect()
        placeholders = ",".join("?" for _ in snapshot_ids)
        try:
            conn.execute(
                """INSERT INTO snapshots
                   (id, deck_path, parent_id, deck_state, timestamp,
                    description, branch, tag, deck_hash, merge_parent_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    replacement.id,
                    replacement.deck_path,
                    replacement.parent_id,
                    replacement.deck_state,
                    replacement.timestamp.isoformat(),
                    replacement.description,
                    replacement.branch,
                    replacement.tag,
                    replacement.deck_hash,
                    replacement.merge_parent_id,
                ),
            )
            conn.execute(
                f"UPDATE snapshots SET parent_id = ? "  # noqa: S608
                f"WHERE parent_id IN ({placeholders}) AND id != ?",
                [replacement.id, *snapshot_ids, replacement.id],
            )
            # Merge-parent edges into the replaced run point at the
            # replacement too. If a replaced snapshot was itself a merge
            # commit, its second-parent ancestry is lost (the replacement
            # is linear) — acceptable for squash.
            conn.execute(
                f"UPDATE snapshots SET merge_parent_id = ? "  # noqa: S608
                f"WHERE merge_parent_id IN ({placeholders}) AND id != ?",
                [replacement.id, *snapshot_ids, replacement.id],
            )
            if update_tip:
                conn.execute(
                    "UPDATE branches SET tip_id = ? WHERE deck_path = ? AND name = ?",
                    (replacement.id, replacement.deck_path, replacement.branch),
                )
            conn.execute(
                f"DELETE FROM snapshots WHERE id IN ({placeholders})",  # noqa: S608
                snapshot_ids,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ── Ancestry operations ───────────────────────────────

    def get_ancestor_ids(self, snapshot_id: str, deck_path: str) -> set[str]:
        """All snapshot ids reachable from snapshot_id (inclusive).

        Follows both parent_id and merge_parent_id, but never leaves the
        given deck_path partition — a parent edge into another deck's
        history is treated as missing.
        """
        conn = self._db.connect()
        visited: set[str] = set()
        frontier = [snapshot_id]
        while frontier:
            current = frontier.pop()
            if current in visited:
                continue
            row = conn.execute(
                "SELECT parent_id, merge_parent_id FROM snapshots"
                " WHERE id = ? AND deck_path = ?",
                (current, deck_path),
            ).fetchone()
            if row is None:
                continue
            visited.add(current)
            for pid in (row["parent_id"], row["merge_parent_id"]):
                if pid is not None and pid not in visited:
                    frontier.append(pid)
        return visited

    def is_ancestor(
        self, ancestor_id: str, descendant_id: str, deck_path: str
    ) -> bool:
        """True if ancestor_id is reachable from descendant_id (or equal)."""
        conn = self._db.connect()
        visited: set[str] = set()
        frontier = [descendant_id]
        while frontier:
            current = frontier.pop()
            if current in visited:
                continue
            visited.add(current)
            row = conn.execute(
                "SELECT parent_id, merge_parent_id FROM snapshots"
                " WHERE id = ? AND deck_path = ?",
                (current, deck_path),
            ).fetchone()
            if row is None:
                continue  # outside this deck's partition — not an ancestor
            if current == ancestor_id:
                return True
            for pid in (row["parent_id"], row["merge_parent_id"]):
                if pid is not None and pid not in visited:
                    frontier.append(pid)
        return False

    def find_merge_base(
        self, id_a: str, id_b: str, deck_path: str
    ) -> str | None:
        """Best common ancestor of two snapshots, or None if unrelated.

        Intersects the two ancestor sets and picks the candidate with the
        greatest (timestamp, id) — deterministic for deck-scale histories.
        """
        common = self.get_ancestor_ids(id_a, deck_path) & self.get_ancestor_ids(
            id_b, deck_path
        )
        if not common:
            return None
        candidates = [
            snap
            for sid in common
            if (snap := self.get_snapshot(sid)) is not None
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda s: (s.timestamp, s.id))
        return best.id

    # ── Branch operations ─────────────────────────────────

    def save_branch(self, branch: VCSBranch) -> None:
        """Insert or update a branch head."""
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO branches
               (name, deck_path, tip_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                branch.name,
                branch.deck_path,
                branch.tip_id,
                branch.created_at.isoformat(),
            ),
        )
        conn.commit()

    def get_branch(self, deck_path: str, name: str) -> VCSBranch | None:
        """Fetch a single branch by name and deck path."""
        conn = self._db.connect()
        row = conn.execute(
            "SELECT * FROM branches WHERE deck_path = ? AND name = ?",
            (deck_path, name),
        ).fetchone()
        if row is None:
            return None
        return _row_to_branch(row)

    def list_branches(self, deck_path: str) -> list[VCSBranch]:
        """List all branches for a deck."""
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT * FROM branches WHERE deck_path = ? ORDER BY name",
            (deck_path,),
        ).fetchall()
        return [_row_to_branch(r) for r in rows]

    def delete_branch(self, deck_path: str, branch_name: str) -> None:
        """Delete a branch (not its snapshots)."""
        conn = self._db.connect()
        conn.execute(
            "DELETE FROM branches WHERE deck_path = ? AND name = ?",
            (deck_path, branch_name),
        )
        conn.commit()

    def update_branch_tip(
        self, deck_path: str, branch_name: str, new_tip_id: str
    ) -> None:
        """Update a branch's tip to point at a new snapshot."""
        conn = self._db.connect()
        conn.execute(
            "UPDATE branches SET tip_id = ? WHERE deck_path = ? AND name = ?",
            (new_tip_id, deck_path, branch_name),
        )
        conn.commit()

    # ── Head (current branch) operations ──────────────────

    def get_head(self, deck_path: str) -> str | None:
        """Return the persisted current branch for a deck, if any."""
        conn = self._db.connect()
        row = conn.execute(
            "SELECT current_branch FROM deck_heads WHERE deck_path = ?",
            (deck_path,),
        ).fetchone()
        return row["current_branch"] if row else None

    def set_head(self, deck_path: str, branch: str) -> None:
        """Persist the current branch for a deck."""
        conn = self._db.connect()
        conn.execute(
            """INSERT OR REPLACE INTO deck_heads (deck_path, current_branch)
               VALUES (?, ?)""",
            (deck_path, branch),
        )
        conn.commit()

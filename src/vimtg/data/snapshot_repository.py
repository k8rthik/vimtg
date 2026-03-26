"""Persistent storage for deck version control snapshots and branches."""

from __future__ import annotations

from datetime import UTC, datetime

from vimtg.data.database import Database
from vimtg.domain.vcs import VCSBranch, VCSSnapshot


def _row_to_snapshot(row: dict) -> VCSSnapshot:
    """Convert a SQLite Row to a VCSSnapshot."""
    return VCSSnapshot(
        id=row["id"],
        deck_path=row["deck_path"],
        parent_id=row["parent_id"],
        deck_state=row["deck_state"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        description=row["description"] or "",
        branch=row["branch"] or "main",
        tag=row["tag"],
        deck_hash=row["deck_hash"] or "",
    )


def _row_to_branch(row: dict) -> VCSBranch:
    """Convert a SQLite Row to a VCSBranch."""
    return VCSBranch(
        name=row["name"],
        deck_path=row["deck_path"],
        tip_id=row["tip_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
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
                description, branch, tag, deck_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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

"""Persistent storage for deck version control snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from vimtg.data.database import Database
from vimtg.domain.vcs import VCSSnapshot


def _parse_timestamp(value: object) -> datetime:
    """Parse a stored ISO timestamp, tolerating malformed rows.

    Always timezone-aware (UTC assumed for a naive value, the epoch
    for garbage): history sorts snapshots by timestamp, and one naive
    row among aware ones would make that comparison raise.
    """
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.min.replace(tzinfo=UTC)


def _row_to_snapshot(row: dict[str, Any]) -> VCSSnapshot:
    """Convert a SQLite Row to a VCSSnapshot."""
    return VCSSnapshot(
        id=row["id"],
        deck_path=row["deck_path"],
        parent_id=row["parent_id"],
        deck_state=row["deck_state"],
        timestamp=_parse_timestamp(row["timestamp"]),
        description=row["description"] or "",
        tag=row["tag"],
        deck_hash=row["deck_hash"] or "",
    )


class SnapshotRepository:
    """SQLite CRUD for persistent deck snapshots."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save_snapshot(self, snapshot: VCSSnapshot) -> None:
        """Insert a snapshot row."""
        conn = self._db.connect()
        conn.execute(
            """INSERT INTO snapshots
               (id, deck_path, parent_id, deck_state, timestamp,
                description, tag, deck_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.id,
                snapshot.deck_path,
                snapshot.parent_id,
                snapshot.deck_state,
                snapshot.timestamp.isoformat(),
                snapshot.description,
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

    def list_snapshots(self, deck_path: str, limit: int = 100) -> list[VCSSnapshot]:
        """List snapshots for a deck, newest first."""
        conn = self._db.connect()
        rows = conn.execute(
            """SELECT * FROM snapshots
               WHERE deck_path = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (deck_path, limit),
        ).fetchall()
        return [_row_to_snapshot(r) for r in rows]

    def tip(self, deck_path: str) -> VCSSnapshot | None:
        """The end of a deck's chain: the snapshot no other snapshot
        descends from (the newest such one, should an old database hold
        several). None before the first commit.

        Chosen by structure, not by timestamp, so a clock step between two
        saves cannot make an older snapshot the tip and fork the chain.
        """
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT id, parent_id, timestamp FROM snapshots WHERE deck_path = ?",
            (deck_path,),
        ).fetchall()
        parents = {row["parent_id"] for row in rows}
        leaves = [row for row in rows if row["id"] not in parents]
        if not leaves:
            return None
        newest = max(
            leaves, key=lambda row: (_parse_timestamp(row["timestamp"]), row["id"])
        )
        return self.get_snapshot(newest["id"])

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

    def update_snapshot_description(self, snapshot_id: str, description: str) -> None:
        conn = self._db.connect()
        conn.execute(
            "UPDATE snapshots SET description = ? WHERE id = ?",
            (description, snapshot_id),
        )
        conn.commit()

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

"""Oracle tags in SQLite: the expanded ``card_tags`` rows search joins
on, and the ``tag_aliases`` it resolves a typed alias through."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator

from vimtg.data.database import Database
from vimtg.domain.oracle_tags import OracleTag, alias_rows, card_tag_rows

LAST_TAG_SYNC_KEY = "last_tag_sync"
_BATCH_SIZE = 20000


class TagRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def replace_all(self, tags: Iterable[OracleTag], synced_at: str) -> int:
        """Reload every tag row from a fresh ``oracle_tags`` file, in one
        transaction with the sync time. Returns the number of tags.

        Refuses an empty tag set: a feed that parsed to nothing is an
        error, not a sync of zero tags, and must not wipe the table.
        """
        tags = list(tags)
        if not tags:
            raise ValueError("no oracle tags to load")
        conn = self._db.connect()
        try:
            conn.execute("DELETE FROM card_tags")
            conn.execute("DELETE FROM tag_aliases")
            for batch in _batches(card_tag_rows(tags)):
                conn.executemany(
                    "INSERT OR IGNORE INTO card_tags (oracle_id, slug) VALUES (?, ?)", batch
                )
            conn.executemany(
                "INSERT OR IGNORE INTO tag_aliases (alias, slug) VALUES (?, ?)",
                list(alias_rows(tags)),
            )
            conn.execute(
                "INSERT OR REPLACE INTO sync_metadata (key, value) VALUES (?, ?)",
                (LAST_TAG_SYNC_KEY, synced_at),
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        return len(tags)

    def count(self) -> int:
        """Expanded ``(card, tag)`` rows."""
        with self._db.reader() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM card_tags").fetchone()
        return int(row["cnt"]) if row else 0

    def has_tags(self) -> bool:
        """True once a tag sync has landed; safe from any thread."""
        with self._db.reader() as conn:
            return conn.execute("SELECT 1 FROM card_tags LIMIT 1").fetchone() is not None

    def get_last_sync(self) -> str | None:
        """ISO time of the last tag sync, None when tags were never synced."""
        conn = self._db.connect()
        row: sqlite3.Row | None = conn.execute(
            "SELECT value FROM sync_metadata WHERE key = ?", (LAST_TAG_SYNC_KEY,)
        ).fetchone()
        return str(row["value"]) if row is not None else None


def _batches(rows: Iterable[tuple[str, str]]) -> Iterator[list[tuple[str, str]]]:
    batch: list[tuple[str, str]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= _BATCH_SIZE:
            yield batch
            batch = []
    if batch:
        yield batch

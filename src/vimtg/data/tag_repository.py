"""Oracle tags in SQLite: the expanded ``card_tags`` rows search joins
on, keyed by the integer ids ``tags`` and ``oracle_ids`` assign, and
the ``tag_aliases`` it resolves a typed alias through."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from itertools import batched

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
        tag_ids = {tag.slug: n for n, tag in enumerate(tags, 1)}
        oracle_ids: dict[str, int] = {}
        conn = self._db.connect()
        try:
            for table in ("card_tags", "tag_aliases", "tags", "oracle_ids"):
                conn.execute(f"DELETE FROM {table}")  # noqa: S608
            conn.executemany(
                "INSERT OR IGNORE INTO tags (id, slug) VALUES (?, ?)",
                [(n, slug) for slug, n in tag_ids.items()],
            )
            for batch in batched(card_tag_rows(tags), _BATCH_SIZE):
                conn.executemany(
                    "INSERT OR IGNORE INTO card_tags (card_oracle, tag_id) VALUES (?, ?)",
                    [
                        (oracle_ids.setdefault(oracle_id, len(oracle_ids) + 1), tag_ids[slug])
                        for oracle_id, slug in batch
                    ],
                )
            conn.executemany(
                "INSERT INTO oracle_ids (id, oracle_id) VALUES (?, ?)",
                [(n, oracle_id) for oracle_id, n in oracle_ids.items()],
            )
            conn.executemany(
                "INSERT OR IGNORE INTO tag_aliases (alias, tag_id) VALUES (?, ?)",
                [(alias, tag_ids[slug]) for alias, slug in alias_rows(tags)],
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

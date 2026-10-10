import sqlite3
from collections.abc import Iterable

from vimtg.data.card_mapper import card_to_row, row_to_card
from vimtg.data.database import Database
from vimtg.data.search_sql import compile_search, fts_name_query, order_by
from vimtg.domain.card import Card
from vimtg.domain.card_names import CardMap, name_aliases, normalize_card_name
from vimtg.domain.search import Node, SearchOrder, ranking_words

_INSERT_SQL = """
    INSERT OR REPLACE INTO cards (
        scryfall_id, name, mana_cost, cmc, type_line, oracle_text,
        colors, color_identity, power, toughness, set_code, rarity,
        price_usd, price_usd_foil, price_eur, price_eur_foil, price_tix,
        legalities, image_uri, layout, keywords,
        oracle_id, produced_mana, game_changer, full_oracle_text, face_stats
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_ALIAS_SQL = """
    INSERT OR IGNORE INTO card_names (name_key, scryfall_id, rank) VALUES (?, ?, ?)
"""

# Best match for each alias key: lowest rank (full name before faces),
# then the most recently inserted row.
_RESOLVE_SQL = """
    SELECT n.name_key AS name_key, c.* FROM card_names n
    JOIN cards c ON c.scryfall_id = n.scryfall_id
    WHERE n.name_key IN ({placeholders})
    ORDER BY n.name_key, n.rank, c.rowid DESC
"""

_BATCH_SIZE = 5000
_VARIABLE_CHUNK = 500


class CardRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def bulk_insert(self, cards: Iterable[Card]) -> int:
        """Insert or update cards, keeping one row per oracle card.

        A card replaces any row with the same scryfall_id or oracle_id,
        so a changed representative printing never leaves a stale twin.
        Rebuilds FTS after. Returns the count inserted.
        """
        conn = self._db.connect()
        try:
            count = self._write_cards(conn, cards, dedupe=True)
            conn.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        return count

    def replace_all(self, cards: Iterable[Card], synced_at: str | None = None) -> int:
        """Reload the whole card table from a fresh sync, atomically.

        Old rows, aliases and FTS entries are replaced in one transaction
        together with the sync timestamp: readers see either the old
        card set or the new one, never a mix, and cards Scryfall dropped
        or re-keyed disappear. Non-card tables are untouched.
        """
        conn = self._db.connect()
        try:
            conn.execute("DELETE FROM card_names")
            conn.execute("DELETE FROM cards")
            count = self._write_cards(conn, cards, dedupe=False)
            conn.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
            if synced_at is not None:
                _write_last_sync(conn, synced_at)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        return count

    def _write_cards(
        self, conn: sqlite3.Connection, cards: Iterable[Card], *, dedupe: bool
    ) -> int:
        count = 0
        batch: list[Card] = []

        def flush() -> None:
            ids = [c.scryfall_id for c in batch]
            if dedupe:
                _delete_superseded(conn, batch)
            for start in range(0, len(ids), _VARIABLE_CHUNK):
                chunk = ids[start : start + _VARIABLE_CHUNK]
                conn.execute(
                    f"DELETE FROM card_names WHERE scryfall_id IN ({_marks(chunk)})",  # noqa: S608
                    chunk,
                )
            conn.executemany(_INSERT_SQL, [card_to_row(c) for c in batch])
            conn.executemany(
                _ALIAS_SQL,
                [
                    (key, c.scryfall_id, rank)
                    for c in batch
                    for key, rank in name_aliases(c.name)
                ],
            )

        for card in cards:
            batch.append(card)
            if len(batch) >= _BATCH_SIZE:
                flush()
                count += len(batch)
                batch = []

        if batch:
            flush()
            count += len(batch)
        return count

    def search(self, query: str, limit: int = 50) -> list[Card]:
        """FTS5 prefix search. Return ranked by relevance."""
        fts_query = _prepare_fts_query(query)
        if not fts_query:
            return []

        with self._db.reader() as conn:
            rows = conn.execute(
                """
                SELECT c.* FROM cards c
                JOIN cards_fts f ON c.rowid = f.rowid
                WHERE cards_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        return [row_to_card(row) for row in rows]

    def get_by_name(self, name: str) -> Card | None:
        """Resolve one name the way every other lookup does.

        Matches the full name or any face, case-, accent- and
        separator-insensitively ("Fire/Ice", "fable of the mirror-breaker").
        """
        return self.get_by_names([name]).get(name)

    def get_by_names(self, names: Iterable[str]) -> CardMap:
        """Resolve many names at once — the single card-name resolver.

        Returns a :class:`CardMap` keyed by normalised name: look cards
        up with the caller's own spelling. The canonical full name of
        each card is keyed too.
        """
        keys = list(dict.fromkeys(normalize_card_name(n) for n in names))
        result = CardMap()
        if not keys:
            return result

        conn = self._db.connect()
        for chunk_start in range(0, len(keys), _VARIABLE_CHUNK):
            chunk = keys[chunk_start : chunk_start + _VARIABLE_CHUNK]
            rows = conn.execute(
                _RESOLVE_SQL.format(placeholders=_marks(chunk)), chunk
            ).fetchall()
            for row in rows:
                key = row["name_key"]
                if key in result:
                    continue  # rows are ordered best match first
                card = row_to_card(row)
                result[key] = card
                result.setdefault(card.name, card)

        return result

    def search_parsed(
        self, query: Node, limit: int = 50, order: SearchOrder | None = None
    ) -> list[Card]:
        """Cards matching a parsed search (vimtg.domain.search).

        Ranked by how well bare name words match, then by name, unless
        ``order`` (order:/direction:) asks for another sort. Runs on
        its own reader connection, so concurrent searches from worker
        threads never share a cursor.
        """
        where, params = compile_search(query)
        words = ranking_words(query)
        if order is not None:
            sql = (
                f"SELECT c.* FROM cards c WHERE {where} "  # noqa: S608
                f"ORDER BY {order_by(order)} LIMIT ?"
            )
            args: list[object] = [*params, limit]
        elif words:
            sql = (
                "SELECT c.* FROM cards c LEFT JOIN ("  # noqa: S608
                "SELECT rowid AS rid, rank AS score FROM cards_fts "
                "WHERE cards_fts MATCH ?) r ON r.rid = c.rowid "
                f"WHERE {where} "
                "ORDER BY r.score IS NULL, r.score, c.name LIMIT ?"
            )
            args = [fts_name_query(words), *params, limit]
        else:
            sql = f"SELECT c.* FROM cards c WHERE {where} ORDER BY c.name LIMIT ?"  # noqa: S608
            args = [*params, limit]
        with self._db.reader() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [row_to_card(row) for row in rows]

    def autocomplete(self, prefix: str, limit: int = 20) -> list[str]:
        """Return distinct card names matching prefix via FTS5."""
        fts_query = _prepare_fts_query(prefix)
        if not fts_query:
            return []

        with self._db.reader() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT c.name FROM cards c
                JOIN cards_fts f ON c.rowid = f.rowid
                WHERE cards_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        return [row["name"] for row in rows]

    def count(self) -> int:
        conn = self._db.connect()
        row = conn.execute("SELECT COUNT(*) as cnt FROM cards").fetchone()
        return row["cnt"] if row else 0

    def get_last_sync(self) -> str | None:
        """Return ISO timestamp from sync_metadata, or None."""
        conn = self._db.connect()
        row = conn.execute(
            "SELECT value FROM sync_metadata WHERE key = 'last_sync'",
        ).fetchone()
        if row is None:
            return None
        value: str | None = row["value"]
        return value

    def set_last_sync(self, timestamp: str) -> None:
        conn = self._db.connect()
        _write_last_sync(conn, timestamp)
        conn.commit()


def _write_last_sync(conn: sqlite3.Connection, timestamp: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO sync_metadata (key, value) VALUES ('last_sync', ?)",
        (timestamp,),
    )


def _marks(values: list[str]) -> str:
    return ",".join("?" for _ in values)


def _delete_superseded(conn: sqlite3.Connection, batch: list[Card]) -> None:
    """Drop rows that an incoming card replaces under a new scryfall_id:
    same oracle_id (a re-keyed representative printing) or, for rows
    without one, the same name."""
    pairs = [(c.oracle_id, c.name, c.scryfall_id) for c in batch]
    conn.executemany(
        "DELETE FROM card_names WHERE scryfall_id IN ("
        "SELECT scryfall_id FROM cards WHERE scryfall_id != ?3 AND "
        "((?1 IS NOT NULL AND oracle_id = ?1) OR name = ?2))",
        pairs,
    )
    conn.executemany(
        "DELETE FROM cards WHERE scryfall_id != ?3 AND "
        "((?1 IS NOT NULL AND oracle_id = ?1) OR name = ?2)",
        pairs,
    )


# The FTS tokenizer strips accents but keeps ligatures as-is.
_FTS_FOLDS = str.maketrans({"Æ": "Ae", "æ": "ae", "Œ": "Oe", "œ": "oe"})


def _prepare_fts_query(query: str) -> str:
    """Build an FTS5 prefix query, quoting each word so punctuation
    in card names (apostrophes, commas, hyphens) is matched literally
    instead of being parsed as FTS5 syntax."""
    words = query.strip().translate(_FTS_FOLDS).split()
    return " ".join(f'"{w.replace(chr(34), chr(34) * 2)}"*' for w in words if w)

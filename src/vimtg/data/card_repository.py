from collections.abc import Iterable

from vimtg.data.card_mapper import card_to_row, row_to_card
from vimtg.data.database import Database
from vimtg.domain.card import Card
from vimtg.domain.search import SearchQuery

_INSERT_SQL = """
    INSERT OR REPLACE INTO cards (
        scryfall_id, name, mana_cost, cmc, type_line, oracle_text,
        colors, color_identity, power, toughness, set_code, rarity,
        price_usd, legalities, image_uri, layout, keywords
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_BATCH_SIZE = 5000


class CardRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def bulk_insert(self, cards: Iterable[Card]) -> int:
        """Insert cards in batches. INSERT OR REPLACE. Rebuild FTS after. Return count."""
        conn = self._db.connect()
        count = 0
        batch: list[tuple[object, ...]] = []

        for card in cards:
            batch.append(card_to_row(card))
            if len(batch) >= _BATCH_SIZE:
                conn.executemany(_INSERT_SQL, batch)
                count += len(batch)
                batch = []

        if batch:
            conn.executemany(_INSERT_SQL, batch)
            count += len(batch)

        conn.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
        conn.commit()
        return count

    def search(self, query: str, limit: int = 50) -> list[Card]:
        """FTS5 prefix search. Return ranked by relevance."""
        fts_query = _prepare_fts_query(query)
        if not fts_query:
            return []

        conn = self._db.connect()
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
        """Case-insensitive exact name match."""
        conn = self._db.connect()
        row = conn.execute(
            "SELECT * FROM cards WHERE name = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
        if row is None:
            return None
        return row_to_card(row)

    def get_by_names(self, names: Iterable[str]) -> dict[str, Card]:
        """Batch lookup. Chunk into groups of 500 for SQLite variable limit."""
        names_list = list(names)
        if not names_list:
            return {}

        conn = self._db.connect()
        result: dict[str, Card] = {}

        for chunk_start in range(0, len(names_list), 500):
            chunk = names_list[chunk_start : chunk_start + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT * FROM cards WHERE name COLLATE NOCASE IN ({placeholders})",  # noqa: S608
                chunk,
            ).fetchall()
            for row in rows:
                card = row_to_card(row)
                result[card.name] = card

        return result

    def search_advanced(self, query: SearchQuery) -> list[Card]:
        """Build SQL from SearchQuery filters."""
        conn = self._db.connect()
        conditions: list[str] = []
        params: list[object] = []

        if query.text:
            conditions.append(
                "c.rowid IN (SELECT rowid FROM cards_fts WHERE cards_fts MATCH ?)"
            )
            words = query.text.strip().split()
            params.append(" ".join(f"{w}*" for w in words))
        if query.type_contains:
            conditions.append("c.type_line LIKE ?")
            params.append(f"%{query.type_contains}%")
        if query.cmc_eq is not None:
            conditions.append("c.cmc = ?")
            params.append(query.cmc_eq)
        if query.cmc_lte is not None:
            conditions.append("c.cmc <= ?")
            params.append(query.cmc_lte)
        if query.cmc_gte is not None:
            conditions.append("c.cmc >= ?")
            params.append(query.cmc_gte)
        if query.set_code:
            conditions.append("c.set_code = ?")
            params.append(query.set_code)
        if query.rarity:
            conditions.append("c.rarity = ?")
            params.append(query.rarity.value)
        if query.oracle_contains:
            conditions.append("c.oracle_text LIKE ?")
            params.append(f"%{query.oracle_contains}%")

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM cards c WHERE {where} LIMIT 50"  # noqa: S608
        rows = conn.execute(sql, params).fetchall()
        return [row_to_card(row) for row in rows]

    def autocomplete(self, prefix: str, limit: int = 20) -> list[str]:
        """Return distinct card names matching prefix via FTS5."""
        fts_query = _prepare_fts_query(prefix)
        if not fts_query:
            return []

        conn = self._db.connect()
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
        return row["value"]

    def set_last_sync(self, timestamp: str) -> None:
        conn = self._db.connect()
        conn.execute(
            "INSERT OR REPLACE INTO sync_metadata (key, value) VALUES ('last_sync', ?)",
            (timestamp,),
        )
        conn.commit()


def _prepare_fts_query(query: str) -> str:
    """Append * to each word for prefix matching."""
    words = query.strip().split()
    return " ".join(f"{w}*" for w in words if w)

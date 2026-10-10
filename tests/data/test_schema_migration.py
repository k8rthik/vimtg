"""Upgrading a v0.8 database (PRAGMA user_version 0) to schema v1."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.schema import SCHEMA_VERSION

# The cards table exactly as v0.8 created it.
_V08_CARDS = """
CREATE TABLE cards (
    scryfall_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    mana_cost TEXT DEFAULT '',
    cmc REAL DEFAULT 0,
    type_line TEXT DEFAULT '',
    oracle_text TEXT DEFAULT '',
    colors TEXT DEFAULT '[]',
    color_identity TEXT DEFAULT '[]',
    power TEXT,
    toughness TEXT,
    set_code TEXT NOT NULL,
    rarity TEXT NOT NULL,
    price_usd REAL,
    price_usd_foil REAL,
    price_eur REAL,
    price_eur_foil REAL,
    price_tix REAL,
    legalities TEXT DEFAULT '{}',
    image_uri TEXT,
    layout TEXT DEFAULT 'normal',
    keywords TEXT DEFAULT '[]'
)
"""

_V08_REST = (
    """CREATE VIRTUAL TABLE cards_fts USING fts5(
        name, type_line, oracle_text,
        content=cards, content_rowid=rowid, tokenize='porter unicode61')""",
    "CREATE TABLE sync_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE snapshots (
        id TEXT PRIMARY KEY, deck_path TEXT NOT NULL, parent_id TEXT,
        deck_state TEXT NOT NULL, timestamp TEXT NOT NULL,
        description TEXT DEFAULT '', branch TEXT DEFAULT 'main', tag TEXT,
        deck_hash TEXT DEFAULT '', merge_parent_id TEXT)""",
    """CREATE TABLE branches (
        name TEXT NOT NULL, deck_path TEXT NOT NULL, tip_id TEXT NOT NULL,
        created_at TEXT NOT NULL, PRIMARY KEY (name, deck_path))""",
    "CREATE TABLE deck_heads (deck_path TEXT PRIMARY KEY, current_branch TEXT NOT NULL)",
)


def _row(scryfall_id: str, name: str, set_code: str, modern: str) -> tuple[object, ...]:
    return (
        scryfall_id, name, "{R}", 1.0, "Instant", "Deal 3.", '["R"]', '["R"]',
        None, None, set_code, "common", 1.0, None, None, None, None,
        json.dumps({"modern": modern}), None, "normal", "[]",
    )


def _make_v08_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(_V08_CARDS)
    for sql in _V08_REST:
        conn.execute(sql)
    rows = [
        # The stale twin v0.8's INSERT OR REPLACE left after a
        # representative-printing change: older rowid, old legality.
        _row("old-bolt", "Lightning Bolt", "old", "legal"),
        _row("fire-ice", "Fire // Ice", "mh2", "legal"),
        _row("new-bolt", "Lightning Bolt", "new", "banned"),
    ]
    conn.executemany(f"INSERT INTO cards VALUES ({','.join('?' * 21)})", rows)
    conn.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
    conn.execute("INSERT INTO sync_metadata VALUES ('last_sync', '2026-10-01T00:00:00+00:00')")
    conn.execute(
        "INSERT INTO snapshots (id, deck_path, deck_state, timestamp, description) "
        "VALUES ('s1', '/burn.deck', '4 Lightning Bolt', '2026-09-01', 'first')"
    )
    conn.execute("INSERT INTO branches VALUES ('main', '/burn.deck', 's1', '2026-09-01')")
    conn.execute("INSERT INTO deck_heads VALUES ('/burn.deck', 'main')")
    conn.commit()
    conn.close()


def test_v08_database_upgrades_in_place(tmp_path: Path) -> None:
    path = tmp_path / "v08.db"
    _make_v08_db(path)

    db = Database(path)
    try:
        db.initialize()
        conn = db.connect()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

        columns = {r[1] for r in conn.execute("PRAGMA table_info(cards)")}
        assert {"oracle_id", "produced_mana", "game_changer"} <= columns

        repo = CardRepository(db)
        # Stale duplicate removed, newest row kept; lookups now agree
        assert repo.count() == 2
        bolts = repo.search("Lightning Bolt")
        assert [c.set_code for c in bolts] == ["new"]
        single = repo.get_by_name("lightning bolt")
        assert single is not None and single.legalities["modern"] == "banned"
        assert repo.get_by_names(["Lightning Bolt"])["Lightning Bolt"] == single
        # Aliases built from stored names, without a re-sync
        fire_ice = repo.get_by_name("Fire/Ice")
        assert fire_ice is not None and fire_ice.name == "Fire // Ice"
        assert repo.get_by_name("Ice") == fire_ice
        # Old rows read back with the new fields defaulted
        assert fire_ice.produced_mana == ()
        assert fire_ice.game_changer is False
        # Last sync forgotten so the next sync backfills new fields
        assert repo.get_last_sync() is None

        # History tables untouched
        snap = conn.execute("SELECT * FROM snapshots").fetchall()
        assert [(r["id"], r["deck_state"], r["description"]) for r in snap] == [
            ("s1", "4 Lightning Bolt", "first")
        ]
        assert conn.execute("SELECT COUNT(*) FROM branches").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM deck_heads").fetchone()[0] == 1
    finally:
        db.close()


def test_migration_runs_once(tmp_path: Path) -> None:
    path = tmp_path / "v08.db"
    _make_v08_db(path)
    db = Database(path)
    try:
        db.initialize()
        repo = CardRepository(db)
        repo.set_last_sync("2026-10-10T00:00:00+00:00")
        db.initialize()  # every app start re-runs initialize
        assert repo.get_last_sync() == "2026-10-10T00:00:00+00:00"
        assert repo.count() == 2
    finally:
        db.close()


def test_fresh_database_starts_at_current_version(tmp_path: Path) -> None:
    db = Database(tmp_path / "fresh.db")
    try:
        db.initialize()
        conn = db.connect()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert CardRepository(db).count() == 0
    finally:
        db.close()

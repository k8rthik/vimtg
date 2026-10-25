"""Upgrading older databases (PRAGMA user_version 0 to 4) to the current schema."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.schema import SCHEMA_VERSION
from vimtg.data.snapshot_repository import SnapshotRepository
from vimtg.domain.card import Card
from vimtg.services.vcs_service import VersionControlService

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
        assert {"oracle_id", "produced_mana", "game_changer",
                "full_oracle_text"} <= columns

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
        assert fire_ice.full_oracle_text == ""
        # Rules-text search falls back to oracle_text until a re-sync
        from vimtg.services.search_service import SearchService

        assert [c.name for c in SearchService(repo).search("o:deal")] == [
            "Fire // Ice", "Lightning Bolt"
        ]
        # Last sync forgotten so the next sync backfills new fields
        assert repo.get_last_sync() is None

        # Snapshots untouched, branch tables gone
        snap = conn.execute("SELECT * FROM snapshots").fetchall()
        assert [(r["id"], r["deck_state"], r["description"]) for r in snap] == [
            ("s1", "4 Lightning Bolt", "first")
        ]
        assert _tables(conn) & {"branches", "deck_heads"} == set()
    finally:
        db.close()


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows}


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


def _make_v1_db(path: Path, *, split_cost: str) -> None:
    """A schema-v1 database: v0.8 tables upgraded, cards as v1 stored
    them (a split card with only its left half's cost)."""
    _make_v08_db(path)
    conn = sqlite3.connect(path)
    for sql in (
        "ALTER TABLE cards ADD COLUMN oracle_id TEXT",
        "ALTER TABLE cards ADD COLUMN produced_mana TEXT DEFAULT '[]'",
        "ALTER TABLE cards ADD COLUMN game_changer INTEGER DEFAULT 0",
        "ALTER TABLE cards ADD COLUMN full_oracle_text TEXT",
        """CREATE TABLE card_names (name_key TEXT NOT NULL,
            scryfall_id TEXT NOT NULL, rank INTEGER NOT NULL,
            PRIMARY KEY (name_key, scryfall_id))""",
    ):
        conn.execute(sql)
    conn.execute("DELETE FROM cards WHERE scryfall_id = 'old-bolt'")
    conn.execute(
        "UPDATE cards SET layout = 'split', mana_cost = ? WHERE scryfall_id = 'fire-ice'",
        (split_cost,),
    )
    conn.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()


def test_v1_split_cost_forces_resync(tmp_path: Path) -> None:
    path = tmp_path / "v1.db"
    _make_v1_db(path, split_cost="{1}{R}")
    db = Database(path)
    try:
        db.initialize()
        conn = db.connect()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        columns = {r[1] for r in conn.execute("PRAGMA table_info(cards)")}
        assert "face_stats" in columns
        repo = CardRepository(db)
        # Left-half-only cost: forget the sync so the next one refreshes
        assert repo.get_last_sync() is None
        assert repo.count() == 2
        # Old rows read back unchanged until that sync
        fire_ice = repo.search("Fire")[0]
        assert fire_ice.mana_cost == "{1}{R}" and fire_ice.face_stats == ()
        # Snapshots untouched, branch tables gone
        assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
        assert _tables(conn) & {"branches", "deck_heads"} == set()
    finally:
        db.close()


def test_v1_with_full_costs_keeps_last_sync(tmp_path: Path) -> None:
    path = tmp_path / "v1.db"
    _make_v1_db(path, split_cost="{1}{R} // {1}{U}")
    db = Database(path)
    try:
        db.initialize()
        assert CardRepository(db).get_last_sync() == "2026-10-01T00:00:00+00:00"
    finally:
        db.close()


def _make_v2_db(path: Path) -> None:
    """A schema-v2 database: branched history tables still present and a
    snapshot recorded on branch main."""
    _make_v1_db(path, split_cost="{1}{R} // {1}{U}")
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE cards ADD COLUMN face_stats TEXT")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()


def test_v2_branch_tables_are_dropped_and_history_still_lists(tmp_path: Path) -> None:
    path = tmp_path / "v2.db"
    _make_v2_db(path)
    db = Database(path)
    try:
        db.initialize()
        conn = db.connect()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert "snapshots" in _tables(conn)
        assert _tables(conn) & {"branches", "deck_heads"} == set()
        vcs = VersionControlService(SnapshotRepository(db), "/burn.deck")
        assert [(s.id, s.description) for s in vcs.get_log()] == [("s1", "first")]
        assert CardRepository(db).get_last_sync() == "2026-10-01T00:00:00+00:00"
    finally:
        db.close()


def test_face_stats_round_trip(
    tmp_path: Path, real_shape_cards: list[dict[str, object]]
) -> None:
    db = Database(tmp_path / "fresh.db")
    try:
        db.initialize()
        repo = CardRepository(db)
        repo.replace_all([Card.from_scryfall(d) for d in real_shape_cards])  # type: ignore[arg-type]
        delver = repo.get_by_name("Delver of Secrets")
        assert delver is not None
        assert delver.face_stats == (("1", "1"), ("3", "2"))
        bolt = repo.get_by_name("Lightning Bolt")
        assert bolt is not None and bolt.face_stats == ()
        fire_ice = repo.get_by_name("Fire // Ice")
        assert fire_ice is not None and fire_ice.mana_cost == "{1}{R} // {1}{U}"
    finally:
        db.close()


def test_v3_database_gains_the_oracle_tag_tables(tmp_path: Path) -> None:
    """A database from before oracle tags upgrades on open: the tag
    tables exist (empty, never synced) and the version is current."""
    from vimtg.data.tag_repository import TagRepository

    path = tmp_path / "cards.db"
    db = Database(path)
    db.initialize()
    conn = db.connect()
    conn.execute("DROP TABLE card_tags")
    conn.execute("DROP TABLE tag_aliases")
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    db.close()

    db = Database(path)
    db.initialize()
    try:
        conn = db.connect()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"card_tags", "tag_aliases"} <= tables
        tags = TagRepository(db)
        assert not tags.has_tags()
        assert tags.get_last_sync() is None
    finally:
        db.close()


def test_v4_text_keyed_tags_are_dropped_and_resync_restores_them(
    real_shape_repo: CardRepository,
) -> None:
    """A v4 database kept the oracle id and slug text in every tag row.
    Opening it under v5 leaves the tags unsynced (the search says so)
    until the next tag sync, which fills the integer-keyed tables and
    makes ``otag:`` searches work again."""
    from tests.tag_support import load_fixture_tags
    from vimtg.data.tag_repository import TagRepository
    from vimtg.services.search_service import SearchService

    db = real_shape_repo.database
    conn = db.connect()
    for table in ("card_tags", "tag_aliases", "tags", "oracle_ids"):
        conn.execute(f"DROP TABLE {table}")
    conn.execute(
        "CREATE TABLE card_tags (oracle_id TEXT NOT NULL, slug TEXT NOT NULL, "
        "PRIMARY KEY (oracle_id, slug)) WITHOUT ROWID"
    )
    conn.execute("CREATE INDEX idx_card_tags_slug ON card_tags(slug)")
    conn.execute("CREATE TABLE tag_aliases (alias TEXT PRIMARY KEY, slug TEXT NOT NULL)")
    sol_ring = real_shape_repo.get_by_name("Sol Ring")
    assert sol_ring is not None
    conn.execute("INSERT INTO card_tags VALUES (?, 'ramp')", (sol_ring.oracle_id,))
    conn.execute("INSERT INTO tag_aliases VALUES ('acceleration', 'ramp')")
    conn.execute(
        "INSERT INTO sync_metadata (key, value) "
        "VALUES ('last_tag_sync', '2026-10-01T00:00:00+00:00')"
    )
    conn.execute("PRAGMA user_version = 4")
    conn.commit()

    db.initialize()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    tags = TagRepository(db)
    assert not tags.has_tags()
    assert tags.get_last_sync() is None
    service = SearchService(real_shape_repo)
    assert service.tags_unsynced("otag:ramp")
    assert service.search("otag:ramp") == []

    load_fixture_tags(real_shape_repo)
    assert not service.tags_unsynced("otag:ramp")
    assert [c.name for c in service.search("otag:ramp")] == ["Sol Ring"]
    assert [c.name for c in service.search("otag:acceleration")] == ["Sol Ring"]

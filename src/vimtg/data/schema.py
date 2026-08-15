import sqlite3

CARDS_TABLE = """
CREATE TABLE IF NOT EXISTS cards (
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

CARDS_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
    name,
    type_line,
    oracle_text,
    content=cards,
    content_rowid=rowid,
    tokenize='porter unicode61'
)
"""

INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name)",
    "CREATE INDEX IF NOT EXISTS idx_cards_cmc ON cards(cmc)",
    "CREATE INDEX IF NOT EXISTS idx_cards_type ON cards(type_line)",
)

SYNC_TABLE = """
CREATE TABLE IF NOT EXISTS sync_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    deck_path TEXT NOT NULL,
    parent_id TEXT,
    deck_state TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    description TEXT DEFAULT '',
    branch TEXT DEFAULT 'main',
    tag TEXT,
    deck_hash TEXT DEFAULT '',
    merge_parent_id TEXT
)
"""

SNAPSHOT_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_snapshots_deck ON snapshots(deck_path)",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_branch ON snapshots(deck_path, branch)",
)

BRANCHES_TABLE = """
CREATE TABLE IF NOT EXISTS branches (
    name TEXT NOT NULL,
    deck_path TEXT NOT NULL,
    tip_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (name, deck_path)
)
"""

DECK_HEADS_TABLE = """
CREATE TABLE IF NOT EXISTS deck_heads (
    deck_path TEXT PRIMARY KEY,
    current_branch TEXT NOT NULL
)
"""


_PRICE_MIGRATIONS = (
    ("price_usd_foil", "ALTER TABLE cards ADD COLUMN price_usd_foil REAL"),
    ("price_eur", "ALTER TABLE cards ADD COLUMN price_eur REAL"),
    ("price_eur_foil", "ALTER TABLE cards ADD COLUMN price_eur_foil REAL"),
    ("price_tix", "ALTER TABLE cards ADD COLUMN price_tix REAL"),
)


_SNAPSHOT_MIGRATIONS = (
    ("deck_hash", "ALTER TABLE snapshots ADD COLUMN deck_hash TEXT DEFAULT ''"),
    ("merge_parent_id", "ALTER TABLE snapshots ADD COLUMN merge_parent_id TEXT"),
)


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Add missing columns to existing databases. Idempotent."""
    # Cards table migrations
    card_rows = conn.execute("PRAGMA table_info(cards)").fetchall()
    card_columns = {row[1] for row in card_rows}
    for col_name, sql in _PRICE_MIGRATIONS:
        if col_name not in card_columns:
            conn.execute(sql)

    # Snapshots table migrations
    snap_rows = conn.execute("PRAGMA table_info(snapshots)").fetchall()
    snap_columns = {row[1] for row in snap_rows}
    for col_name, sql in _SNAPSHOT_MIGRATIONS:
        if col_name not in snap_columns:
            conn.execute(sql)

    conn.commit()


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.execute(CARDS_TABLE)
    conn.execute(CARDS_FTS)
    for idx in INDEXES:
        conn.execute(idx)
    conn.execute(SYNC_TABLE)
    conn.execute(SNAPSHOTS_TABLE)
    for idx in SNAPSHOT_INDEXES:
        conn.execute(idx)
    conn.execute(BRANCHES_TABLE)
    conn.execute(DECK_HEADS_TABLE)
    conn.commit()
    _run_migrations(conn)

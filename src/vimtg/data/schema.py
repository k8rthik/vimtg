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


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.execute(CARDS_TABLE)
    conn.execute(CARDS_FTS)
    for idx in INDEXES:
        conn.execute(idx)
    conn.execute(SYNC_TABLE)
    conn.commit()

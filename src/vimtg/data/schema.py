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
    keywords TEXT DEFAULT '[]',
    oracle_id TEXT,
    produced_mana TEXT DEFAULT '[]',
    game_changer INTEGER DEFAULT 0,
    full_oracle_text TEXT,
    face_stats TEXT
)
"""

# Every normalised spelling a card resolves under (full name, each face),
# see vimtg.domain.card_names. Rebuilt with the cards table on each sync.
CARD_NAMES_TABLE = """
CREATE TABLE IF NOT EXISTS card_names (
    name_key TEXT NOT NULL,
    scryfall_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    PRIMARY KEY (name_key, scryfall_id)
)
"""

CARD_NAMES_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_card_names_id ON card_names(scryfall_id)",
)

# Scryfall oracle tags (otag:), expanded at load time so a card tagged
# with a leaf tag has a row for every ancestor tag too. card_tags is
# all integers: a tags row id and an oracle_ids row id. Only the tag
# load writes oracle_ids, in the same transaction as card_tags, so a
# resync of the cards table cannot leave a card_tags row pointing at
# the wrong card. card_tags is keyed tag first so one tag's rows share
# a few pages: a search probes it once per candidate card.
TAG_TABLES = (
    """CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY,
        slug TEXT NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS tag_aliases (
        alias TEXT PRIMARY KEY,
        tag_id INTEGER NOT NULL
    ) WITHOUT ROWID""",
    """CREATE TABLE IF NOT EXISTS oracle_ids (
        oracle_id TEXT PRIMARY KEY,
        id INTEGER NOT NULL
    ) WITHOUT ROWID""",
    """CREATE TABLE IF NOT EXISTS card_tags (
        card_oracle INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        PRIMARY KEY (tag_id, card_oracle)
    ) WITHOUT ROWID""",
)

# Bumped whenever a migration needs to run once against an existing DB.
#   0 -> v0.8 and earlier (no PRAGMA user_version set)
#   1 -> oracle_id / produced_mana / game_changer, card_names aliases,
#        stale duplicate card rows removed
#   2 -> split cards store both halves' cost ("{1}{R} // {1}{U}"),
#        face_stats (per-face power/toughness)
#   3 -> deck history is linear: the branches and deck_heads tables are
#        dropped
#   4 -> card_tags and tag_aliases (Scryfall oracle tags)
#   5 -> tag tables keyed by integer ids (tags, oracle_ids)
SCHEMA_VERSION = 5

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

# branch and merge_parent_id are unread since v3 and kept at their
# defaults: dropping a column rebuilds the table for nothing.
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
)


_PRICE_MIGRATIONS = (
    ("price_usd_foil", "ALTER TABLE cards ADD COLUMN price_usd_foil REAL"),
    ("price_eur", "ALTER TABLE cards ADD COLUMN price_eur REAL"),
    ("price_eur_foil", "ALTER TABLE cards ADD COLUMN price_eur_foil REAL"),
    ("price_tix", "ALTER TABLE cards ADD COLUMN price_tix REAL"),
)


_CARD_V1_MIGRATIONS = (
    ("oracle_id", "ALTER TABLE cards ADD COLUMN oracle_id TEXT"),
    ("produced_mana", "ALTER TABLE cards ADD COLUMN produced_mana TEXT DEFAULT '[]'"),
    ("game_changer", "ALTER TABLE cards ADD COLUMN game_changer INTEGER DEFAULT 0"),
    # Every face's rules text, for search; NULL until the next sync
    # (search falls back to oracle_text).
    ("full_oracle_text", "ALTER TABLE cards ADD COLUMN full_oracle_text TEXT"),
    # Per-face [power, toughness] as JSON; NULL until the next sync
    # (search falls back to the front face's power/toughness).
    ("face_stats", "ALTER TABLE cards ADD COLUMN face_stats TEXT"),
)


_SNAPSHOT_MIGRATIONS = (
    ("deck_hash", "ALTER TABLE snapshots ADD COLUMN deck_hash TEXT DEFAULT ''"),
)


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Add missing columns to existing databases. Idempotent."""
    # Cards table migrations
    card_rows = conn.execute("PRAGMA table_info(cards)").fetchall()
    card_columns = {row[1] for row in card_rows}
    for col_name, sql in (*_PRICE_MIGRATIONS, *_CARD_V1_MIGRATIONS):
        if col_name not in card_columns:
            conn.execute(sql)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_oracle ON cards(oracle_id)")

    # Snapshots table migrations
    snap_rows = conn.execute("PRAGMA table_info(snapshots)").fetchall()
    snap_columns = {row[1] for row in snap_rows}
    for col_name, sql in _SNAPSHOT_MIGRATIONS:
        if col_name not in snap_columns:
            conn.execute(sql)

    conn.commit()

    version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        _migrate_to_v1(conn)
    if version < 2:
        _migrate_to_v2(conn)
    if version < 3:
        _migrate_to_v3(conn)
    if version < 4:
        _migrate_to_v4(conn)
    if version < 5:
        _migrate_to_v5(conn)


def _migrate_to_v1(conn: sqlite3.Connection) -> None:
    """One-time upgrade of a v0.8 database, in a single transaction.

    Only the card tables change; snapshots, branches and deck heads are
    left exactly as they were.

    * Stale duplicates: v0.8 synced with INSERT OR REPLACE keyed on
      scryfall_id, so a changed representative printing left the old
      row behind. Keep the most recently inserted row per name.
    * Build the card_names alias table from the stored full names.
    * Forget the last sync time when cards exist, so the next sync
      backfills the new columns and the face colours v0.8 dropped.
    """
    from vimtg.domain.card_names import name_aliases

    try:
        removed = conn.execute(
            "DELETE FROM cards WHERE rowid NOT IN "
            "(SELECT MAX(rowid) FROM cards GROUP BY name COLLATE NOCASE)"
        ).rowcount
        conn.execute("DELETE FROM card_names")
        rows = conn.execute("SELECT scryfall_id, name FROM cards").fetchall()
        conn.executemany(
            "INSERT OR IGNORE INTO card_names (name_key, scryfall_id, rank) "
            "VALUES (?, ?, ?)",
            [
                (key, row[0], rank)
                for row in rows
                for key, rank in name_aliases(row[1])
            ],
        )
        if removed:
            conn.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
        if rows:
            conn.execute("DELETE FROM sync_metadata WHERE key = 'last_sync'")
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """Rows stored before v2 lack data only Scryfall has: a split
    card's right-half cost, a multi-face card's per-face power and
    toughness.

    When any such row exists, forget the last sync so the next
    (automatic) sync rebuilds the cards table; until then everything
    reads the old values. Card tables only; history tables are not
    touched.
    """
    try:
        stale = conn.execute(
            "SELECT 1 FROM cards WHERE (layout = 'split' "
            "AND COALESCE(mana_cost, '') NOT LIKE '% // %') "
            "OR (layout IN ('transform', 'modal_dfc', 'meld', 'flip', "
            "'adventure', 'reversible_card') AND face_stats IS NULL) LIMIT 1"
        ).fetchone()
        if stale is not None:
            conn.execute("DELETE FROM sync_metadata WHERE key = 'last_sync'")
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _migrate_to_v3(conn: sqlite3.Connection) -> None:
    """Deck history became one chain per deck: the branch heads and the
    current-branch pointer have nothing left to point at. Snapshots are
    not touched; every row that was on a branch stays in the table."""
    try:
        conn.execute("DROP TABLE IF EXISTS branches")
        conn.execute("DROP TABLE IF EXISTS deck_heads")
        conn.execute("DROP INDEX IF EXISTS idx_snapshots_branch")
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _migrate_to_v4(conn: sqlite3.Connection) -> None:
    """Oracle tags arrive in their own tables, empty until the next
    sync downloads the tags file; cards and history are untouched."""
    try:
        for sql in TAG_TABLES:
            conn.execute(sql)
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _migrate_to_v5(conn: sqlite3.Connection) -> None:
    """The v4 tag tables repeated the oracle id and slug text in every
    row; v5 keys them by integer ids. The old tables are dropped and
    the empty v5 ones take their place, so an ``otag:`` search says
    the tags are not synced until the next sync fills them. Cards and
    history are untouched."""
    try:
        conn.execute("DROP TABLE IF EXISTS card_tags")
        conn.execute("DROP TABLE IF EXISTS tag_aliases")
        for sql in TAG_TABLES:
            conn.execute(sql)
        conn.execute("DELETE FROM sync_metadata WHERE key = 'last_tag_sync'")
        conn.execute("PRAGMA user_version = 5")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.execute(CARDS_TABLE)
    conn.execute(CARDS_FTS)
    for idx in INDEXES:
        conn.execute(idx)
    conn.execute(CARD_NAMES_TABLE)
    for idx in CARD_NAMES_INDEXES:
        conn.execute(idx)
    for sql in TAG_TABLES:
        conn.execute(sql)
    conn.execute(SYNC_TABLE)
    conn.execute(SNAPSHOTS_TABLE)
    for idx in SNAPSHOT_INDEXES:
        conn.execute(idx)
    conn.commit()
    _run_migrations(conn)

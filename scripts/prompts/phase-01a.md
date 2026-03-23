You are building vimtg — a TUI-based MTG deck builder. This is Phase 1a: Card domain model, database manager, and schema.

Read `PROGRESS.md` for context on what exists. The project skeleton is already set up with pyproject.toml, CLI, and test infrastructure.

## 1. Card Domain Model — `src/vimtg/domain/card.py`

Create frozen dataclasses:

```python
class Color(Enum):
    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"

class Rarity(Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    MYTHIC = "mythic"
    SPECIAL = "special"
    BONUS = "bonus"

@dataclass(frozen=True)
class Card:
    scryfall_id: str
    name: str
    mana_cost: str
    cmc: float
    type_line: str
    oracle_text: str
    colors: tuple[Color, ...]
    color_identity: tuple[Color, ...]
    power: str | None
    toughness: str | None
    set_code: str
    rarity: Rarity
    price_usd: float | None
    legalities: dict[str, str]
    image_uri: str | None
    layout: str
    keywords: tuple[str, ...]
```

Add a `from_scryfall(data: dict) -> Card` class method that handles:
- **Normal cards**: all fields from top level
- **Transform/MDFC** (`layout` in `transform`, `modal_dfc`): use `card_faces[0]` for mana_cost, oracle_text, power, toughness. Name is the full `name` field (e.g., "Delver of Secrets // Insectile Aberration")
- **Split cards** (`layout == "split"`): use full name, combine oracle_text from both faces
- **Adventure cards** (`layout == "adventure"`): use `card_faces[0]` for the creature, combine oracle text
- Missing `prices.usd` → `None`
- Missing `image_uris` → check `card_faces[0].image_uris`, else `None`
- `colors` and `color_identity` are lists of strings ["W","U"] → convert to `tuple[Color, ...]`
- `legalities` is a dict like `{"standard": "legal", "modern": "not_legal"}` — keep as-is
- `keywords` is a list → tuple

Also add helper methods:
- `is_creature` → bool (checks type_line)
- `is_land` → bool
- `is_instant_or_sorcery` → bool
- `color_symbol` → str like "{W}{U}" for display
- `mana_pips` → dict[Color, int] counting pips in mana_cost

## 2. Database Manager — `src/vimtg/data/database.py`

```python
class Database:
    """SQLite connection manager with WAL mode and proper lifecycle."""

    def __init__(self, db_path: Path) -> None: ...
    def connect(self) -> sqlite3.Connection: ...
    def close(self) -> None: ...
    def __enter__(self) -> sqlite3.Connection: ...
    def __exit__(self, ...) -> None: ...
```

- WAL journal mode for concurrent read access
- Foreign keys enabled
- Row factory = `sqlite3.Row`
- Create parent directories on first connect
- `initialize()` method runs schema creation

## 3. Schema — `src/vimtg/data/schema.py`

SQL DDL as string constants:

```sql
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
);

CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
    name,
    type_line,
    oracle_text,
    content=cards,
    content_rowid=rowid,
    tokenize='porter unicode61'
);

CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);
CREATE INDEX IF NOT EXISTS idx_cards_cmc ON cards(cmc);
CREATE INDEX IF NOT EXISTS idx_cards_type ON cards(type_line);

CREATE TABLE IF NOT EXISTS sync_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Function: `initialize_schema(conn: sqlite3.Connection) -> None` — execute all DDL.

## Tests — TDD

Write tests FIRST, then implement to pass them.

`tests/domain/test_card.py` (15+ test cases):
- `test_from_scryfall_normal_creature` — Goblin Guide with all fields
- `test_from_scryfall_instant` — Lightning Bolt
- `test_from_scryfall_transform_card` — Delver of Secrets, verify name includes both faces
- `test_from_scryfall_split_card` — Fire // Ice, verify combined oracle text
- `test_from_scryfall_adventure_card` — Bonecrusher Giant
- `test_from_scryfall_missing_price` — card with no USD price → None
- `test_from_scryfall_missing_image` — card with no image_uris → fallback to card_faces
- `test_from_scryfall_special_characters` — Jötun Grunt with unicode
- `test_is_creature` — true for creatures, false for instants
- `test_is_land` — true for lands
- `test_color_symbol` — verify formatting
- `test_mana_pips` — parse "{2}{R}{R}" → {RED: 2}
- `test_card_is_frozen` — cannot modify after creation
- `test_from_scryfall_with_keywords` — verify keywords tuple

Use the fixture data from `tests/fixtures/scryfall_sample.json`.

`tests/data/test_database.py`:
- `test_database_creates_file` — verify db file created
- `test_database_wal_mode` — verify WAL journal mode
- `test_schema_initialization` — verify tables exist after init
- `test_schema_idempotent` — running init twice doesn't error

## IMPORTANT

- All dataclasses MUST be frozen (immutable)
- No mutation — factory methods return new objects
- Use `tuple` not `list` for collection fields (frozen requirement)
- Handle ALL Scryfall card layouts — this is the most critical parser in the project
- Keep each file under 200 lines

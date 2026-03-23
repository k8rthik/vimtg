You are building vimtg — a TUI-based MTG deck builder. This is Phase 1b: CardRepository with FTS5 full-text search.

Read `PROGRESS.md` for context. Phase 1a created: Card domain model (`src/vimtg/domain/card.py`), Database manager (`src/vimtg/data/database.py`), Schema (`src/vimtg/data/schema.py`).

Read the existing files to understand the data model before writing new code.

## CardRepository — `src/vimtg/data/card_repository.py`

```python
class CardRepository:
    def __init__(self, db: Database) -> None: ...

    def bulk_insert(self, cards: Iterable[Card]) -> int:
        """Insert cards in batches of 5000. Returns count inserted.
        Uses INSERT OR REPLACE for idempotency. Rebuilds FTS index after."""

    def search(self, query: str, limit: int = 50) -> list[Card]:
        """FTS5 prefix search. 'light' matches 'Lightning Bolt'.
        Returns ranked by relevance. Must complete in <50ms for 1000+ cards."""

    def get_by_name(self, name: str) -> Card | None:
        """Exact name match (case-insensitive)."""

    def get_by_names(self, names: Iterable[str]) -> dict[str, Card]:
        """Batch lookup. Returns {name: Card} for found names.
        Chunks queries to respect SQLite variable limit."""

    def autocomplete(self, prefix: str, limit: int = 20) -> list[str]:
        """Return distinct card names matching prefix. For typeahead."""

    def count(self) -> int:
        """Total card count in database."""

    def get_last_sync(self) -> str | None:
        """Return ISO timestamp of last sync, or None."""

    def set_last_sync(self, timestamp: str) -> None:
        """Record sync timestamp."""
```

### Implementation details

**bulk_insert**: Serialize Card fields to match schema columns. `colors` and `color_identity` stored as JSON arrays (e.g., `'["W","U"]'`). `legalities` stored as JSON object. `keywords` stored as JSON array. Use `executemany` with batching.

After inserting cards, rebuild FTS index:
```sql
INSERT INTO cards_fts(cards_fts) VALUES('rebuild');
```

**search**: Use FTS5 MATCH with prefix queries:
```sql
SELECT c.* FROM cards c
JOIN cards_fts f ON c.rowid = f.rowid
WHERE cards_fts MATCH ?
ORDER BY rank
LIMIT ?
```
Append `*` to query terms for prefix matching: `"lightning bolt"` → `"lightning* bolt*"`. Handle single-word and multi-word queries.

**get_by_names**: SQLite has a limit of 999 variables per query. Chunk the names list into groups of 500 and use `WHERE LOWER(name) IN (...)`.

**Row to Card conversion**: Create a private `_row_to_card(row: sqlite3.Row) -> Card` method that deserializes JSON fields back to Python types.

## Domain search model — `src/vimtg/domain/search.py`

```python
@dataclass(frozen=True)
class SearchQuery:
    text: str = ""                          # Free text (FTS)
    type_contains: str | None = None        # t:creature
    colors_include: tuple[Color, ...] = ()  # c:red
    cmc_eq: float | None = None             # cmc=3
    cmc_lte: float | None = None            # cmc<=3
    cmc_gte: float | None = None            # cmc>=3
    set_code: str | None = None             # set:mh2
    rarity: Rarity | None = None            # r:mythic
    oracle_contains: str | None = None      # o:"draw a card"
    name_exact: str | None = None           # !name

    def is_empty(self) -> bool: ...
```

## Tests — TDD

Write tests FIRST in `tests/data/test_card_repository.py`:

- `test_bulk_insert_returns_count` — insert 10 cards, verify count == 10
- `test_bulk_insert_idempotent` — insert same cards twice, count stays same
- `test_search_by_name` — search "Lightning Bolt" returns exact match first
- `test_search_prefix` — search "light" returns Lightning Bolt
- `test_search_multiword` — search "goblin guide" returns Goblin Guide
- `test_search_limit` — verify limit parameter works
- `test_search_empty_query` — returns empty list
- `test_get_by_name_exact` — exact match returns card
- `test_get_by_name_case_insensitive` — "lightning bolt" matches "Lightning Bolt"
- `test_get_by_name_not_found` — returns None
- `test_get_by_names_batch` — lookup multiple names at once
- `test_get_by_names_partial` — some found, some not
- `test_autocomplete` — prefix "Gob" returns "Goblin Guide"
- `test_count` — matches inserted count
- `test_sync_metadata` — set and get last sync timestamp
- `test_search_performance` — insert 1000 cards, search completes in <100ms (use `time.perf_counter`)

Fixture: Use `scryfall_sample.json` to create test cards. Also create a `conftest.py` fixture `card_repo` that returns a CardRepository with sample data pre-loaded.

## IMPORTANT

- The search MUST be fast — FTS5 with prefix matching
- All Card objects returned must be fully hydrated (all fields populated)
- JSON serialization/deserialization must be lossless
- No mutation — CardRepository methods return new objects, never modify inputs
- Keep file under 200 lines. If it exceeds, extract `_row_to_card` into a separate `card_mapper.py`

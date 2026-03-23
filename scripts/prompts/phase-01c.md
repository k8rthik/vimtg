You are building vimtg — a TUI-based MTG deck builder. This is Phase 1c: Scryfall sync, SearchService, and CLI commands.

Read `PROGRESS.md` and existing source files for context. Phase 1a/1b created: Card model, Database, Schema, CardRepository with FTS5 search.

## 1. Scryfall Sync — `src/vimtg/data/scryfall_sync.py`

```python
class ScryfallSync:
    """Downloads Scryfall bulk data and loads into local SQLite."""

    BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
    USER_AGENT = "vimtg/0.1.0 (https://github.com/vimtg/vimtg)"

    def __init__(self, card_repo: CardRepository, cache_dir: Path) -> None: ...

    async def get_bulk_data_url(self) -> str:
        """Fetch bulk-data manifest, return download URL for 'oracle_cards'."""

    async def download(self, url: str, dest: Path, progress: Callable[[int, int], None] | None = None) -> Path:
        """Stream download to temp file, atomic rename to dest. Returns dest path.
        progress callback receives (bytes_downloaded, total_bytes)."""

    def parse_and_load(self, json_path: Path, progress: Callable[[int, int], None] | None = None) -> int:
        """Parse bulk JSON, convert to Card objects, bulk insert. Returns card count.
        Process in streaming chunks — don't load entire JSON into memory.
        progress callback receives (cards_processed, total_estimated)."""

    async def sync(self, progress: Callable[[str, int, int], None] | None = None) -> int:
        """Full sync: download if needed, parse, load. Returns card count.
        progress callback receives (stage, current, total) where stage is
        'download', 'parse', or 'load'."""
```

### Implementation details

- Use `httpx.AsyncClient` for downloads with streaming
- Set `User-Agent` header (Scryfall requires this)
- Download to temp file first, then atomic rename (prevents corruption on crash)
- Use `json.JSONDecoder` with streaming or `ijson` for memory-efficient parsing. If `ijson` isn't available, fall back to loading full JSON (it's ~35MB for oracle_cards, manageable)
- Skip cards where `layout` is `"token"`, `"double_faced_token"`, `"emblem"`, or `"art_series"`
- Batch inserts via CardRepository.bulk_insert
- Record sync timestamp via CardRepository.set_last_sync

**Add `ijson` to pyproject.toml dependencies** (it's a streaming JSON parser).

## 2. SearchService — `src/vimtg/services/search_service.py`

```python
class SearchService:
    """Card search with Scryfall-syntax support."""

    def __init__(self, card_repo: CardRepository) -> None: ...

    def fuzzy_search(self, query: str, limit: int = 20) -> list[Card]:
        """Simple text search — delegates to CardRepository.search."""

    def advanced_search(self, query: str) -> list[Card]:
        """Parse Scryfall-like syntax and search.
        Supported operators: t:, c:, cmc=, cmc<=, cmc>=, o:, set:, r:, !name"""

    def autocomplete(self, prefix: str) -> list[str]:
        """Card name completion."""

    def parse_query(self, raw: str) -> SearchQuery:
        """Parse Scryfall syntax into SearchQuery.
        Examples:
          't:creature c:red cmc<=3'  → SearchQuery(type_contains='creature', colors_include=(RED,), cmc_lte=3)
          'o:"draw a card"'          → SearchQuery(oracle_contains='draw a card')
          'lightning bolt'           → SearchQuery(text='lightning bolt')
          't:instant set:mh2'       → SearchQuery(type_contains='instant', set_code='mh2')
        """
```

### Query parser

Use a simple tokenizer — split on spaces, but respect quoted strings (`o:"draw a card"`). For each token:
- `t:X` or `type:X` → `type_contains = X`
- `c:X` or `color:X` → parse color letters (r→RED, u→BLUE, etc.) into `colors_include`
- `cmc=N`, `cmc<=N`, `cmc>=N` → numeric filter
- `o:"text"` or `oracle:"text"` → `oracle_contains`
- `set:XXX` → `set_code`
- `r:X` or `rarity:X` → `rarity`
- `!name` → `name_exact` (exact match)
- Everything else → appended to `text` field (FTS search)

Add a `search_advanced` method to `CardRepository` that builds a SQL query from a `SearchQuery`:
```sql
SELECT c.* FROM cards c
LEFT JOIN cards_fts f ON c.rowid = f.rowid
WHERE 1=1
  AND (? IS NULL OR cards_fts MATCH ?)       -- text search
  AND (? IS NULL OR c.type_line LIKE ?)      -- type filter
  AND (? IS NULL OR c.cmc <= ?)              -- cmc filter
  ...
ORDER BY rank
LIMIT 50
```

## 3. SyncService — `src/vimtg/services/sync_service.py`

```python
class SyncService:
    """Orchestrates Scryfall data synchronization."""

    def __init__(self, scryfall_sync: ScryfallSync, card_repo: CardRepository) -> None: ...

    async def sync(self, force: bool = False) -> int:
        """Run sync if needed (>24h since last sync or force=True)."""

    def needs_sync(self) -> bool:
        """True if no sync has been done or last sync was >24h ago."""
```

## 4. CLI Commands — extend `src/vimtg/cli.py`

Add to the Click group:

```python
@main.command()
@click.option("--force", is_flag=True, help="Force re-download even if recent")
def sync(force: bool) -> None:
    """Download card data from Scryfall."""
    # Create Database, CardRepository, ScryfallSync
    # Run sync with Rich progress bar
    # Print summary: "Synced N cards in X seconds"

@main.command()
@click.argument("query")
@click.option("--advanced", "-a", is_flag=True, help="Use Scryfall syntax")
@click.option("--limit", "-n", default=20, help="Max results")
def search(query: str, advanced: bool, limit: int) -> None:
    """Search for cards."""
    # Use SearchService
    # Print results as a text-column table matching the TUI aesthetic:
    #   Name                    Mana    Type              Set   Price
    #   Lightning Bolt          {R}     Instant           STA   $1.50
    #   Lightning Helix         {R}{W}  Instant           RAV   $0.50
    # Use Rich for formatting but keep it text-focused (no boxes/panels)
```

The search output should feel like the TUI — same text-column format. This is important for visual cohesion.

## Tests — TDD

`tests/data/test_scryfall_sync.py`:
- `test_parse_and_load` — parse scryfall_sample.json, verify cards loaded into repo
- `test_parse_skips_tokens` — verify token cards are skipped
- `test_parse_handles_all_layouts` — all 10 sample cards parse successfully
- Mock httpx for download tests (don't hit real Scryfall in tests)

`tests/services/test_search_service.py`:
- `test_fuzzy_search` — "bolt" finds Lightning Bolt
- `test_parse_query_type` — `"t:creature"` → SearchQuery(type_contains="creature")
- `test_parse_query_color` — `"c:red"` → SearchQuery(colors_include=(RED,))
- `test_parse_query_cmc` — `"cmc<=3"` → SearchQuery(cmc_lte=3.0)
- `test_parse_query_oracle` — `'o:"draw a card"'` → SearchQuery(oracle_contains="draw a card")
- `test_parse_query_combined` — `"t:creature c:red cmc<=3"` → all three filters
- `test_parse_query_plain_text` — `"lightning bolt"` → SearchQuery(text="lightning bolt")
- `test_advanced_search_type_filter` — only returns creatures
- `test_advanced_search_cmc_filter` — only returns cmc <= 3
- `test_autocomplete` — "Gob" returns ["Goblin Guide"]

## IMPORTANT

- httpx async client for network operations
- Streaming download — do not load entire file into memory
- Atomic file operations (temp + rename) for crash safety
- Search output must be text-column formatted (cohesive with TUI vision)
- All new dependencies added to pyproject.toml
- Run all existing tests after implementation to verify nothing broke

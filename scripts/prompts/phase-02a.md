You are building vimtg — a TUI-based MTG deck builder. This is Phase 2a: Deck domain model and format parser.

Read `PROGRESS.md` and existing source files (especially `src/vimtg/domain/card.py`) for context.

## 1. Deck Domain Model — `src/vimtg/domain/deck.py`

```python
class DeckSection(Enum):
    MAIN = "main"
    SIDEBOARD = "sideboard"
    COMMANDER = "commander"
    COMPANION = "companion"

@dataclass(frozen=True)
class DeckEntry:
    quantity: int
    card_name: str
    section: DeckSection

@dataclass(frozen=True)
class CommentLine:
    line_number: int
    text: str

@dataclass(frozen=True)
class DeckMetadata:
    name: str = ""
    format: str = ""
    author: str = ""
    description: str = ""

@dataclass(frozen=True)
class Deck:
    metadata: DeckMetadata
    entries: tuple[DeckEntry, ...]
    comments: tuple[CommentLine, ...]

    def total_cards(self) -> int: ...
    def mainboard(self) -> tuple[DeckEntry, ...]: ...
    def sideboard(self) -> tuple[DeckEntry, ...]: ...
    def unique_card_names(self) -> frozenset[str]: ...

    def add_entry(self, entry: DeckEntry) -> "Deck":
        """Return new Deck with entry added. If card already exists in same section, increment quantity."""

    def remove_entry(self, card_name: str, section: DeckSection) -> "Deck":
        """Return new Deck with entry removed."""

    def update_quantity(self, card_name: str, section: DeckSection, quantity: int) -> "Deck":
        """Return new Deck with updated quantity. Removes entry if quantity <= 0."""
```

ALL methods return NEW Deck instances. Never mutate.

## 2. Deck Parser — `src/vimtg/data/deck_repository.py`

### Parser: `parse_deck_text(text: str) -> Deck`

Line-by-line parser with these rules:

1. **Metadata comments** (first block of `//` lines with `Key: Value`):
   - `// Deck: Burn` → metadata.name = "Burn"
   - `// Format: modern` → metadata.format = "modern"
   - `// Author: keerthik` → metadata.author = "keerthik"
   - `// Description: Fast aggro` → metadata.description

2. **Section header comments**: `// Creatures`, `// Spells`, `// Lands`, `// Sideboard` — stored as CommentLine

3. **Regular comments**: any other `//` line → CommentLine

4. **Blank lines**: preserved (important for section separation)

5. **Sideboard entries**: `SB: 4 Lightning Bolt` → DeckEntry(4, "Lightning Bolt", SIDEBOARD)

6. **Commander entries**: `CMD: 1 Atraxa, Praetors' Voice` → DeckEntry(1, "Atraxa, Praetors' Voice", COMMANDER)

7. **Main deck entries**: `4 Lightning Bolt` → DeckEntry(4, "Lightning Bolt", MAIN)
   - Pattern: `^\s*(\d+)\s+(.+)$`
   - Card names may contain commas, apostrophes, slashes: "Fire // Ice", "Liliana, the Last Hope", "Lim-Dûl's Vault"

8. **Error handling**: invalid lines (no quantity, non-numeric) → skip with warning, don't crash

### Serializer: `serialize_deck(deck: Deck, original_text: str | None = None) -> str`

If `original_text` is provided, preserve the exact formatting (comments, blank lines, order) and only update quantities/entries that changed. This is critical for round-trip fidelity.

If `original_text` is None, generate from scratch:
```
// Deck: {name}
// Format: {format}

{entries grouped by section, separated by blank lines}

// Sideboard
SB: {qty} {name}
```

### DeckRepository

```python
class DeckRepository:
    def load(self, path: Path) -> str:
        """Read deck file, return raw text."""

    def save(self, path: Path, text: str) -> None:
        """Atomic write: write to temp file, then rename."""

    def list_decks(self, directory: Path) -> list[Path]:
        """Find all .deck files in directory."""

    def exists(self, path: Path) -> bool: ...
```

## Tests — TDD

`tests/domain/test_deck.py`:
- `test_deck_total_cards` — 4+4+4 = 12
- `test_deck_mainboard_filter` — only MAIN entries
- `test_deck_sideboard_filter` — only SIDEBOARD entries
- `test_deck_unique_names` — frozenset of unique card names
- `test_add_entry_new` — adding new card creates new Deck
- `test_add_entry_existing` — adding existing card increments quantity
- `test_add_entry_immutable` — original Deck unchanged
- `test_remove_entry` — removes card, returns new Deck
- `test_remove_entry_not_found` — returns same Deck
- `test_update_quantity` — changes quantity
- `test_update_quantity_zero` — removes entry

`tests/data/test_deck_repository.py`:
- `test_parse_sample_deck` — parse sample_burn.deck, verify all entries
- `test_parse_metadata` — verify name, format, author extracted
- `test_parse_comments_preserved` — all `//` lines stored as CommentLine
- `test_parse_sideboard` — SB: prefix parsed correctly
- `test_parse_card_with_comma` — "Atraxa, Praetors' Voice" parsed correctly
- `test_parse_card_with_slash` — "Fire // Ice" parsed correctly (not confused with comment)
- `test_parse_blank_lines` — blank lines don't cause errors
- `test_parse_invalid_line` — gracefully skips malformed lines
- `test_serialize_roundtrip` — parse(serialize(parse(text))) == parse(text)
- **`test_serialize_exact_roundtrip`** — serialize(parse(text), original_text=text) == text EXACTLY (byte-for-byte). This is the most important test.
- `test_load_and_save` — load file, save to new path, content matches
- `test_save_atomic` — verify temp file approach (file exists even if process crashes)
- `test_list_decks` — finds .deck files in directory

The exact round-trip test is CRITICAL. The parser must preserve formatting perfectly.

## IMPORTANT

- The parser must handle real-world deck files with messy formatting
- Card names can contain ANY character except newlines: commas, apostrophes, slashes, unicode, hyphens
- `// ` at start of line is always a comment — but `//` within a card name (like "Fire // Ice") must be handled. Solution: `SB:` and `CMD:` prefixes and `N ` quantity prefix distinguish entries from comments
- Atomic file writes (temp + rename) for crash safety
- All dataclasses frozen, all methods return new objects
- Keep files under 200 lines

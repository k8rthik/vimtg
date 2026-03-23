You are building vimtg — a TUI-based MTG deck builder. This is Phase 9: Import/export for MTGO, Arena, Moxfield, and Archidekt formats.

Read `PROGRESS.md` and existing source files for context.

## 1. Import/Export Service — `src/vimtg/services/import_export_service.py`

```python
class DeckFormat(Enum):
    VIMTG = "vimtg"      # Native .deck format
    MTGO = "mtgo"         # MTGO text format
    ARENA = "arena"       # MTG Arena export
    MOXFIELD = "moxfield" # Moxfield CSV
    ARCHIDEKT = "archidekt" # Archidekt CSV

class ImportExportService:
    def __init__(self, card_repo: CardRepository) -> None: ...

    def detect_format(self, text: str) -> DeckFormat:
        """Auto-detect format from content.
        - Contains '// Deck:' or 'SB:' → VIMTG
        - Contains '(XXX) NNN' set/collector patterns → ARENA
        - Contains 'Sideboard' header without SB: prefix → MTGO
        - Contains CSV header row → MOXFIELD or ARCHIDEKT
        - Fallback → MTGO (most permissive parser)
        """

    def import_deck(self, text: str, fmt: DeckFormat | None = None) -> Deck:
        """Import deck from text. Auto-detects format if not specified."""

    def export_deck(self, deck: Deck, fmt: DeckFormat, resolved: dict[str, Card] | None = None) -> str:
        """Export deck to text in specified format."""
```

### MTGO Format

Import:
```
4 Lightning Bolt
4 Goblin Guide
20 Mountain

Sideboard
2 Rest in Peace
3 Kor Firewalker
```
- Lines are `N CardName`
- `Sideboard` header switches to sideboard zone
- Blank lines are separators

Export: same format. Group mainboard, blank line, `Sideboard` header, sideboard entries.

### Arena Format

Import:
```
Deck
4 Lightning Bolt (STA) 62
4 Goblin Guide (ZEN) 126
20 Mountain (BLB) 278

Sideboard
2 Rest in Peace (AKR) 33
```
- Lines are `N CardName (SET) CollectorNumber`
- `Deck` and `Sideboard` headers
- Set code and collector number are optional on import

Export:
- Requires resolved cards for set code and collector number
- If card not resolved, omit set/collector info
- Format: `N CardName (SET) CollectorNumber`

### Moxfield CSV

Import:
```csv
Count,Name,Edition,Collector Number,Foil,Section
4,Lightning Bolt,STA,62,,mainboard
2,Rest in Peace,AKR,33,,sideboard
```
- Standard CSV with header row
- Section column: mainboard, sideboard, commander, companion, maybeboard
- Foil, Edition, Collector Number are optional

Export:
- Generate CSV with header
- Use csv module for proper escaping (card names may contain commas)

### Archidekt CSV

Import:
```csv
Quantity,Name,Categories
4,Lightning Bolt,Removal
2,Rest in Peace,Graveyard Hate
```
- Simpler CSV format
- Categories column is informational (not used for import)

Export: Generate with Quantity, Name columns.

### Card name resolution on import

When importing, card names might not exactly match the database:
- Try exact match first
- Try case-insensitive match
- Try fuzzy match (first result from FTS5 search)
- If no match, keep the original name and flag as unresolved

Report unresolved cards as warnings.

## 2. CLI Commands — extend `src/vimtg/cli.py`

```python
@main.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--from", "from_fmt", type=click.Choice(["mtgo", "arena", "moxfield", "archidekt"]))
@click.option("--to", "to_fmt", type=click.Choice(["vimtg", "mtgo", "arena", "moxfield", "archidekt"]), required=True)
@click.option("--output", "-o", type=click.Path())
def convert(input_path: str, from_fmt: str | None, to_fmt: str, output: str | None) -> None:
    """Convert deck between formats.

    Examples:
      vimtg convert burn.txt --to vimtg -o burn.deck
      vimtg convert burn.deck --to arena
      vimtg convert export.csv --from moxfield --to vimtg
    """
    # Auto-detect input format if --from not specified
    # Convert via ImportExportService
    # Write to output file or stdout
    # Print summary: "Converted 60 cards (3 unresolved)"
```

## 3. TUI Commands — extend `deck_cmds.py`

```python
def cmd_export(buffer, cursor, cmd, ctx):
    """:export format [filename]
    :export arena          → print to message area
    :export arena burn.txt → save to file
    :export mtgo           → print MTGO format
    """

def cmd_import(buffer, cursor, cmd, ctx):
    """:import filename — Import deck from file, replacing current buffer.
    Auto-detects format. Shows warning for unresolved cards."""

def cmd_clipboard(buffer, cursor, cmd, ctx):
    """:clipboard [format] — Copy deck to system clipboard in specified format.
    Default: arena format (most commonly pasted into online tools).
    Uses OSC52 escape sequence for terminal clipboard access."""
```

### OSC52 clipboard

```python
def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard via OSC52 escape sequence.
    Works in most modern terminals (iTerm2, kitty, Alacritty, Windows Terminal).
    Returns True if the escape was sent (doesn't guarantee clipboard access)."""
    import base64, sys
    encoded = base64.b64encode(text.encode()).decode()
    sys.stdout.write(f"\033]52;c;{encoded}\007")
    sys.stdout.flush()
    return True
```

## Tests — TDD

`tests/services/test_import_export_service.py`:
- `test_detect_vimtg` — detects native format
- `test_detect_arena` — detects Arena format
- `test_detect_mtgo` — detects MTGO format
- `test_detect_csv` — detects CSV formats

MTGO:
- `test_import_mtgo` — parses MTGO format correctly
- `test_import_mtgo_sideboard` — sideboard section parsed
- `test_export_mtgo` — correct output format
- `test_roundtrip_mtgo` — import then export preserves content

Arena:
- `test_import_arena` — parses set codes and collector numbers
- `test_import_arena_no_set` — handles missing set info
- `test_export_arena` — includes set codes from resolved cards
- `test_roundtrip_arena` — import then export preserves content

Moxfield CSV:
- `test_import_moxfield` — parses CSV with all columns
- `test_export_moxfield` — generates valid CSV
- `test_moxfield_escaped_comma` — card names with commas handled

Cross-format:
- `test_vimtg_to_arena` — convert native to Arena
- `test_arena_to_vimtg` — convert Arena to native
- `test_unresolved_cards` — warns about unresolved names

CLI:
- `test_convert_command` — basic conversion works
- `test_convert_auto_detect` — format detection works
- `test_convert_to_stdout` — output to terminal when no -o flag

## IMPORTANT

- Format detection must be robust — users will paste deck lists from anywhere
- CSV parsing must handle card names with commas (use csv module, not split)
- Arena format requires resolved cards for export (set code + collector number)
- OSC52 clipboard is best-effort — degrade gracefully if terminal doesn't support it
- The convert CLI should feel fast and output clean text (no Rich decorations)
- Keep files under 200 lines

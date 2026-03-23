You are building vimtg — a TUI-based MTG deck builder. This is Phase 2b: DeckService and CLI commands.

Read `PROGRESS.md` and existing source files for context. Phase 2a created the Deck model and parser.

## 1. DeckService — `src/vimtg/services/deck_service.py`

```python
@dataclass(frozen=True)
class ValidationError:
    level: str          # "error" | "warning"
    message: str
    line_number: int | None = None

class DeckService:
    def __init__(self, deck_repo: DeckRepository, card_repo: CardRepository) -> None: ...

    def open_deck(self, path: Path) -> tuple[str, Deck]:
        """Load file, parse into Deck. Returns (raw_text, deck)."""

    def save_deck(self, text: str, path: Path) -> None:
        """Save raw text to file via DeckRepository."""

    def new_deck(self, name: str, fmt: str = "", author: str = "") -> str:
        """Create template deck text with metadata headers. Returns text."""

    def resolve_cards(self, deck: Deck) -> tuple[dict[str, Card], list[str]]:
        """Batch lookup all card names. Returns (found_cards, unresolved_names).
        Uses CardRepository.get_by_names for efficient batch lookup."""

    def validate(self, deck: Deck, resolved: dict[str, Card] | None = None) -> list[ValidationError]:
        """Validate deck. Checks:
        - Quantities > 0
        - Quantities <= 4 for non-basic-lands (warning, not error)
        - Card names resolve (if resolved dict provided)
        - Mainboard has >= 60 cards (warning)
        - Sideboard has <= 15 cards (warning)
        Returns list of ValidationError."""
```

## 2. CLI Commands — extend `src/vimtg/cli.py`

```python
@main.command()
@click.argument("name")
@click.option("--format", "-f", "fmt", default="", help="MTG format (modern, standard, etc.)")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def new(name: str, fmt: str, output: str | None) -> None:
    """Create a new deck file."""
    # Generate template text via DeckService.new_deck
    # Save to output path (default: {name}.deck in current directory)
    # Print: "Created {path}"

@main.command()
@click.argument("path", type=click.Path(exists=True))
def validate(path: str) -> None:
    """Validate a deck file."""
    # Load and parse deck
    # Resolve cards (if database exists)
    # Run validation
    # Print errors and warnings in vim-style format:
    #   burn.deck:5: warning: Goblin Guide not found in database
    #   burn.deck: warning: mainboard has 56 cards (minimum 60)
    # Exit code 1 if any errors, 0 if only warnings

@main.command()
@click.argument("path", type=click.Path(exists=True))
def info(path: str) -> None:
    """Show deck summary."""
    # Load and parse
    # Print text-column summary:
    #   Deck: Burn
    #   Format: modern
    #   Mainboard: 40 cards (24 unique)
    #   Sideboard: 15 cards (7 unique)
    #   Unresolved: 0 cards
```

Output format must be text-focused — no Rich panels or boxes. Just clean columnar text that matches the TUI aesthetic.

## Tests — TDD

`tests/services/test_deck_service.py`:
- `test_open_deck` — load sample_burn.deck, verify Deck object
- `test_save_deck` — save then re-load, content matches
- `test_new_deck` — template has metadata headers
- `test_new_deck_parseable` — parse(new_deck(...)) succeeds
- `test_resolve_cards` — with loaded database, resolves known cards
- `test_resolve_cards_unresolved` — unknown cards in unresolved list
- `test_validate_valid_deck` — no errors for well-formed deck
- `test_validate_over_four_copies` — warning for >4 of non-basic
- `test_validate_zero_quantity` — error for 0 quantity
- `test_validate_small_mainboard` — warning for <60 cards
- `test_validate_large_sideboard` — warning for >15 sideboard

CLI tests in `tests/test_cli.py`:
- `test_new_creates_file` — `vimtg new "Test Deck"` creates file
- `test_validate_valid` — exit code 0 for valid deck
- `test_info_output` — verify output contains card count

Use Click's `CliRunner` for CLI tests.

## IMPORTANT

- Validation output uses vim-style `file:line: level: message` format — this is intentional visual cohesion
- CLI output is text-only, no Rich decorations (panels, boxes, trees)
- All service methods are pure or clearly separated I/O
- DeckService doesn't store state — it's a stateless service layer
- Basic lands detection: "Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes" and snow variants

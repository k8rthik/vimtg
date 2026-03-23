You are building vimtg — a TUI-based MTG deck builder. This is Phase 10: Polish, help system, error handling, config, and packaging.

Read `PROGRESS.md` and existing source files for context. This is the final phase — make everything production-ready.

## 1. Built-in Help System

### Help screen — `src/vimtg/tui/screens/help_screen.py`

```python
class HelpScreen(Screen):
    """Full-screen help overlay, navigable with j/k, dismissible with q."""
```

`:help` or `F1` opens the help screen showing:

```
═══ vimtg Help ═══════════════════════════════════════

NAVIGATION
  j/k         Move down/up
  h/l         Move left/right
  gg/G        Go to first/last line
  w/b         Next/previous card entry
  {/}         Next/previous section
  Ctrl-D/U    Half page down/up

EDITING
  i/a         Insert mode (at cursor / after)
  o/O         Open new line below/above
  dd          Delete card line
  yy          Yank (copy) card line
  p/P         Paste below/above
  +/-         Increment/decrement quantity
  .           Repeat last change
  u/Ctrl-R    Undo/redo

VISUAL MODE
  v/V         Enter visual/visual-line mode
  d/y         Delete/yank selection
  Escape      Exit visual mode

COMMANDS
  :w          Save deck
  :q          Quit (:q! to force)
  :wq         Save and quit
  :e file     Open deck file
  :sort field Sort by name/cmc/type/color/price
  :stats      Toggle analytics panel
  :search q   Search cards
  :%s/a/b/g   Substitute across deck
  :g/pat/cmd  Global command on matching lines
  :export fmt Export (arena/mtgo/moxfield)
  :history    Show undo history
  :help       This screen
  :help cmd   Help for specific command

Press q to close.
```

### Per-command help

`:help sort` shows detailed help for the sort command:
```
:sort [field]     Sort cards in current section

Fields: name (default), cmc, type, color, price, qty
Flags:  :sort!  reverse sort
Range:  :5,10sort cmc  sort lines 5-10

Examples:
  :sort cmc        Sort current section by mana cost
  :%sort name      Sort entire deck alphabetically
  :sort! price     Sort by price, most expensive first
```

Store help text as a dict in `src/vimtg/editor/help_text.py` — one entry per command.

## 2. Error Handling Audit

Review and improve error handling across the entire codebase:

### User-facing errors (vim-style messages)

```python
# Standard vim error format
E37: No write since last change (add ! to override)
E32: No file name
E94: No matching buffer for 'xyz.deck'
W10: Warning: Changing a readonly file

# vimtg-specific
E100: Card database not initialized (run 'vimtg sync' first)
E101: Card not found: 'Lightening Bolt' (did you mean 'Lightning Bolt'?)
E102: Invalid deck format at line 5
W100: 3 cards not found in database
```

### "Did you mean?" suggestions

When a card name isn't found:
1. Run fuzzy search on the misspelled name
2. If top result has high similarity, suggest it: `E101: Card not found: 'Lightening Bolt' (did you mean 'Lightning Bolt'?)`
3. Use a simple Levenshtein distance or FTS5 best match

### Error recovery

- File not found → clear message with path
- Database not initialized → prompt to run `vimtg sync`
- Network error during sync → show error, suggest retry or offline mode
- Invalid deck format → show line number and what's wrong
- Permission denied → clear OS error message

### Implement error types — `src/vimtg/domain/errors.py`

```python
class VimTGError(Exception):
    """Base error with vim-style error code."""
    def __init__(self, code: str, message: str) -> None: ...

class DatabaseNotInitialized(VimTGError): ...
class CardNotFound(VimTGError): ...
class DeckParseError(VimTGError): ...
class UnsavedChangesError(VimTGError): ...
```

## 3. Performance Optimization

Profile and optimize:

1. **Search performance**: Verify FTS5 queries complete in <50ms with full database. Run `EXPLAIN QUERY PLAN` on search queries. Add missing indexes if needed.

2. **Render performance**: Profile DeckView.render(). Ensure <16ms per frame. Only re-render visible lines. Cache Rich renderables that haven't changed.

3. **Startup time**: Lazy-load card database (don't connect until needed). Profile import chain. Target <1s cold start.

4. **Buffer operations**: Verify Buffer operations (insert, delete, set_line) are <1ms for 500-line decks.

Add a simple benchmark that can be run manually:
```python
# tests/test_performance.py
def test_search_performance(card_repo_with_data):
    """Search must complete in <100ms (relaxed for test DB)."""
    import time
    start = time.perf_counter()
    results = card_repo_with_data.search("lightning bolt")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1

def test_buffer_operation_performance():
    """Buffer operations must be <10ms."""
    buffer = Buffer.from_text(large_deck_text)  # 200 lines
    start = time.perf_counter()
    for i in range(100):
        buffer = buffer.set_line(50, "4 New Card")
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0  # 100 ops in <1s = <10ms each
```

## 4. Configuration File — extend `src/vimtg/config/settings.py`

Support `~/.config/vimtg/config.toml`:

```toml
[editor]
theme = "dark"
auto_expand = true
search_limit = 50
default_format = ""

[keybindings]
# Custom bindings (override defaults)
# "ctrl_s" = ":w"
# "ctrl_q" = ":q"

[sync]
auto_remind = true
remind_days = 7

[display]
mana_symbols = true    # Show {R} or just R
column_widths = "auto" # "auto" or "fixed"
```

Parse with `tomllib` (stdlib in 3.11+). Fall back to defaults for missing keys.

## 5. README — `README.md`

Write a README that matches the tool's aesthetic — clean, text-focused, no bloat:

```markdown
# vimtg

Vim-powered Magic: The Gathering deck builder for the terminal.

## Install

    pipx install vimtg

## Quick Start

    vimtg sync                    # Download card database
    vimtg edit my-deck.deck       # Open deck editor
    vimtg search "lightning bolt" # Search cards

## Features

- **Vim keybindings**: hjkl navigation, operators (dd, yy, p), visual mode, macros
- **Offline card search**: 30,000+ cards searchable in <50ms via local SQLite
- **Plain text decks**: Git-friendly .deck format with round-trip fidelity
- **Inline card details**: Auto-expanding card info follows your cursor
- **Undo tree**: Branch and checkpoint your deck iterations
- **Bulk operations**: `:g/t:creature/sort cmc`, `:%s/Bolt/Helix/g`
- **Multi-deck editing**: Open multiple decks, `:bufdo` across all
- **Import/export**: MTGO, Arena, Moxfield, Archidekt formats
- **Deck analytics**: Mana curve, color distribution, price totals

## Deck Format

    // Deck: Burn
    // Format: modern

    // Creatures
    4 Goblin Guide
    4 Monastery Swiftspear

    // Spells
    4 Lightning Bolt

    // Sideboard
    SB: 2 Rest in Peace

## Keybindings

[link to docs/keybindings.md]

## License

MIT
```

## 6. Documentation — `docs/`

Create:
- `docs/keybindings.md` — comprehensive keybinding reference
- `docs/commands.md` — all ex commands with examples
- `docs/deck-format.md` — .deck format specification

## 7. Packaging Verification

Ensure:
1. `pip install -e ".[dev]"` works
2. `pip install .` works (from clean venv)
3. `pipx install .` works
4. `vimtg --version` prints correct version
5. `vimtg --help` shows all subcommands
6. `python -m vimtg` works
7. Entry point in pyproject.toml is correct

Run `python -m build` to verify wheel builds.

## Tests

`tests/test_performance.py`:
- Performance benchmarks (search, buffer ops)

`tests/domain/test_errors.py`:
- `test_error_codes` — correct formatting
- `test_did_you_mean` — suggests close matches

Update `tests/test_smoke.py`:
- `test_full_workflow` — sync → edit → add card → save → validate → export

## Process

1. Implement the help system first
2. Add error types and improve error messages across codebase
3. Add performance tests
4. Add config file support
5. Write README and docs
6. Verify packaging
7. Run full test suite: `pytest --cov=vimtg --cov-fail-under=80`
8. Run lint: `ruff check src/ tests/`
9. Run type check: `mypy src/`

## IMPORTANT

- This is the POLISH phase — don't add new features, refine existing ones
- Error messages must feel like vim: `E{code}: message`
- Help text is stored as data, not generated — we control every word
- The README is the first thing people see — it should sell the tool's philosophy
- Performance matters: search <50ms, render <16ms, startup <1s
- Don't over-document — docs should be reference material, not tutorials
- Final verification: clean install in fresh venv must work end-to-end

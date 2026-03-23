You are building vimtg — a TUI-based MTG deck builder. This is Phase 8a: Global command, substitute, and filter with pipes.

Read `PROGRESS.md` and existing source files for context. This phase adds the vim power commands that make vimtg exceptional for bulk deck editing.

## 1. Global Command — `src/vimtg/editor/command_handlers/filter.py`

```python
def cmd_global(buffer, cursor, cmd, ctx):
    """:g/pattern/cmd — Execute cmd on every line matching pattern.

    Examples:
      :g/Bolt/d            → delete all lines containing "Bolt"
      :g/t:creature/sort   → sort all creature lines (requires card resolution)
      :v/SB:/d             → delete all non-sideboard lines

    Pattern types:
    1. Plain text: :g/Bolt/d — regex match on line text
    2. Card property: :g/t:creature/d — match by card type (resolves cards)
       Supports: t:, c:, cmc=, cmc<=, cmc>=, r: (same as search syntax)

    Process:
    1. Parse pattern and command from :g/pattern/cmd format
    2. Find all matching lines
    3. Execute cmd on each matching line (in reverse order for deletes)
    """

def cmd_global_inverse(buffer, cursor, cmd, ctx):
    """:v/pattern/cmd — Execute cmd on every line NOT matching pattern."""
```

### Pattern matching

For plain text patterns, use regex match on the full line text.

For property-based patterns (starting with `t:`, `c:`, `cmc`, `r:`):
1. Parse the pattern using the SearchQuery parser from Phase 1
2. For each card line, resolve the card name against the database
3. Check if the card matches the filter

### Command execution within :g

Supported sub-commands:
- `d` — delete the line
- `m{target}` — move line (e.g., `m0` = move to top, `m$` = move to bottom)
- `s/old/new/` — substitute on the line
- `sort` — collect matching lines and sort them (special case)

Execute in reverse line order for deletions (so line numbers don't shift).

## 2. Substitute — `src/vimtg/editor/command_handlers/substitute.py`

```python
def cmd_substitute(buffer, cursor, cmd, ctx):
    """:s/old/new/[flags] — Substitute text in card entries.

    Flags:
      g — replace all occurrences (on each line in range)
      c — confirm each replacement (interactive)
      i — case-insensitive

    Ranges:
      :s/old/new/      → current line only
      :%s/old/new/g    → whole file
      :5,10s/old/new/g → line range
      :'<,'>s/old/new/ → visual selection

    Card-name-aware:
      :%s/Lightning Bolt/Chain Lightning/g
      → Validates that 'Chain Lightning' exists in the card database
      → If not found, warns but still performs the substitution

    The substitution operates on the full line text, so it can change:
    - Card names: '4 Lightning Bolt' → '4 Chain Lightning'
    - Quantities: ':s/4/3/' changes quantity
    - Sideboard prefix: ':s/SB: //' removes sideboard prefix

    Parse the s/old/new/flags format:
    - Delimiter is first char after 's' (usually /)
    - Handle escaped delimiters: s/a\\/b/c/ matches 'a/b'
    """

def parse_substitute(args: str) -> tuple[str, str, str]:
    """Parse substitute args into (pattern, replacement, flags).
    Handle arbitrary delimiter (first char of args)."""
```

### Confirm mode (`:s/old/new/gc`)

When `c` flag is present, for each match:
1. Highlight the match in the deck view
2. Show prompt at bottom: `replace with 'new'? [y/n/a/q]`
3. `y` = yes this one, `n` = skip, `a` = all remaining, `q` = quit substitution
4. Update buffer after each confirmation

For now, implement without interactive confirm (just `g` and `i` flags). Add `c` as a placeholder that behaves like `g`.

## 3. Filter with Pipes — extend `filter.py`

```python
def cmd_filter(buffer, cursor, cmd, ctx):
    """:filter pattern — Show only lines matching pattern (view filter).

    This doesn't modify the buffer — it hides non-matching lines.
    The actual Buffer is unchanged; the DeckView renders only visible lines.

    :filter t:creature    → show only creatures
    :filter cmc>=4        → show only 4+ CMC cards
    :filter!              → clear filter (show all)

    Pipe syntax:
    :filter t:creature | sort cmc
    → First filter to creatures, then sort them by CMC
    → Pipe splits the command, each stage receives output of previous
    """
```

### Filter implementation

Add a `view_filter` to the editor state:
```python
@dataclass(frozen=True)
class ViewFilter:
    pattern: str
    visible_lines: frozenset[int]  # Line indices that pass the filter
```

DeckView checks the filter when rendering — hidden lines are not displayed. The Buffer itself is unchanged.

### Pipe implementation

Split command on ` | ` (space-pipe-space). Execute each command in sequence, each operating on the filtered view from the previous.

For Phase 8a, support 2 stages max: `filter | sort` or `filter | cmd`.

## Tests — TDD

`tests/editor/command_handlers/test_filter.py`:
- `test_global_delete` — `:g/Bolt/d` removes matching lines
- `test_global_inverse` — `:v/SB:/d` removes non-sideboard lines
- `test_global_property_type` — `:g/t:creature/d` removes creatures (with card resolution)
- `test_global_reverse_order` — deletions happen bottom-up
- `test_global_move` — `:g/t:land/m$` moves lands to bottom

`tests/editor/command_handlers/test_substitute.py`:
- `test_substitute_single` — `:s/Bolt/Helix/` replaces on current line
- `test_substitute_global` — `:%s/Bolt/Helix/g` replaces in whole file
- `test_substitute_range` — `:5,10s/Bolt/Helix/g` replaces in range
- `test_substitute_card_name` — full card name swap
- `test_substitute_quantity` — `:s/4/3/` changes quantity
- `test_substitute_case_insensitive` — `i` flag works
- `test_substitute_escaped_delimiter` — handles `/` in pattern
- `test_parse_substitute` — correct parsing of s/old/new/flags

`tests/editor/command_handlers/test_view_filter.py`:
- `test_filter_by_text` — shows only matching lines
- `test_filter_clear` — `:filter!` removes filter
- `test_filter_property` — `:filter t:creature` shows creatures only
- `test_pipe_filter_sort` — `:filter t:creature | sort cmc` works

## IMPORTANT

- `:g/pattern/cmd` is vim's most powerful command — get this right
- Property-based patterns (t:, c:, cmc) make this deck-specific, not just generic text
- Substitute validates card names against the database — warns if replacement doesn't exist
- Filter is a VIEW operation — it doesn't modify the buffer, just hides lines
- Pipe syntax is limited (2 stages) — keep it simple and functional
- Execute global deletes in reverse order to avoid line number shifting
- Keep files under 200 lines

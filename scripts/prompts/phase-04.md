You are building vimtg — a TUI-based MTG deck builder. This is Phase 4: Insert mode with fuzzy card search and inline expansion.

Read `PROGRESS.md` and existing source files for context. The TUI is already running with NORMAL mode navigation.

## 1. Search Results Widget — `src/vimtg/tui/widgets/search_results.py`

Floating overlay that appears during INSERT mode when typing a card name.

```python
class SearchResults(Static):
    """Floating search results overlay for card name completion.

    Appears below the cursor line in INSERT mode.
    Shows matching cards as text columns (same format as deck view).
    """

    results: reactive[list[Card]]
    selected_index: reactive[int]
    visible: reactive[bool]
    query: reactive[str]

    def render(self) -> RenderableType:
        """Render search results as aligned text columns:

        ┌─ Search: "bolt" ─────────────────────────────────┐
        │  Lightning Bolt          {R}     Instant          │
        │> Thunderbolt             {1}{R}  Instant          │
        │  Searing Blaze           {R}{R}  Instant          │
        │  Lava Spike              {R}     Sorcery          │
        │  ... (16 more)                                    │
        └──────────────────────────────────────────────────┘

        Selected item (>) shows inline expansion below:
        │    Instant
        │    Thunderbolt deals 3 damage to target creature with flying.
        │    Set: 7ED  Rarity: Common  Price: $0.25
        """

    def select_next(self) -> None: ...
    def select_prev(self) -> None: ...
    def get_selected(self) -> Card | None: ...
    def update_results(self, results: list[Card]) -> None: ...
```

### Behavior

- Appears after typing 2+ characters in INSERT mode
- 100ms debounce before searching (don't search on every keystroke)
- Max 20 results visible, scrollable
- Selected result shows inline expansion (same format as deck view expansion)
- Ctrl-N / Ctrl-P or Tab / Shift-Tab to navigate
- Enter to confirm selection
- Escape dismisses overlay AND exits insert mode
- Continues filtering as you type more characters

## 2. Enhanced Inline Expansion — extend `src/vimtg/tui/widgets/deck_view.py`

Enhance the Phase 3c expansion to show richer card details:

```
> 4    Lightning Bolt          {R}     Instant
  │    Instant
  │    Lightning Bolt deals 3 damage to any target.
  │    Set: STA  Rarity: Uncommon  Price: $1.50
```

For creatures:
```
> 4    Goblin Guide            {R}     Creature — Goblin Scout  2/2
  │    Creature — Goblin Scout
  │    Whenever Goblin Guide attacks, defending player reveals the top
  │    card of their library. If it's a land card, that player puts it
  │    into their hand.
  │    Set: ZEN  Rarity: Rare  Price: $3.50
```

- Oracle text wraps at terminal width minus indent
- P/T shown on collapsed line for creatures
- Keywords could be shown as tags if present
- Auto-expand follows cursor as user navigates with j/k

## 3. Insert Mode Handler — extend `src/vimtg/tui/screens/main_screen.py`

Wire up insert mode:

```python
def _enter_insert_mode(self, variant: str) -> None:
    """Enter INSERT mode.
    variant: 'i' (at cursor), 'a' (after), 'o' (new line below), 'O' (new line above), 'A' (end of line)
    """

def _handle_insert_key(self, key: str) -> None:
    """Handle keystrokes in INSERT mode.
    - Printable chars: accumulate into search query, update SearchResults
    - Ctrl-N/Tab: select next result
    - Ctrl-P/Shift-Tab: select previous result
    - Enter: confirm selected card, insert into buffer
    - Escape: exit insert mode, hide search overlay
    - Backspace: delete last char from query
    - Digits (before any alpha): set quantity prefix (e.g., "4" then search for card)
    """

def _insert_card(self, card: Card, quantity: int = 1) -> None:
    """Insert a card entry into the buffer at the appropriate position.
    Creates new BufferLine like '4 Lightning Bolt' and inserts into buffer.
    """
```

### Insert variants

- `i`: Start editing the current line (if on a card line, edit the card name)
- `a`: Same as `i` but cursor after current text
- `o`: Insert new blank line below cursor, start typing card name
- `O`: Insert new blank line above cursor, start typing card name
- `A`: Edit at end of current line

For `o`/`O` (most common for adding cards):
1. A new blank line appears
2. User types card name → SearchResults appears
3. User selects card → line becomes `1 CardName`
4. User can type a number BEFORE searching to set quantity: type `4`, then search, then select → `4 CardName`

## 4. Quantity Editing — `src/vimtg/editor/operators.py`

```python
def increment_quantity(buffer: Buffer, cursor: Cursor) -> Buffer:
    """Increment the quantity of the card at cursor line. Returns new Buffer.
    If not on a card line, no-op (return same buffer)."""

def decrement_quantity(buffer: Buffer, cursor: Cursor) -> tuple[Buffer, Cursor]:
    """Decrement quantity. If quantity reaches 0, delete the line.
    Returns (new_buffer, new_cursor) — cursor may move if line deleted."""

def set_quantity(buffer: Buffer, cursor: Cursor, qty: int) -> Buffer:
    """Set quantity to specific value. If qty <= 0, delete line."""
```

Normal mode bindings:
- `+` or `Ctrl-A`: increment quantity
- `-` or `Ctrl-X`: decrement quantity (delete at 0)

These are deck-specific operations that feel native to the tool — not generic text editing.

## 5. Async Search with Debounce

```python
# In MainScreen or a dedicated search controller

import asyncio

class SearchController:
    """Manages debounced async card search for insert mode."""

    def __init__(self, search_service: SearchService, results_widget: SearchResults) -> None: ...

    async def on_query_change(self, query: str) -> None:
        """Called when search text changes. Debounces and searches."""
        self._pending_query = query
        if self._debounce_task:
            self._debounce_task.cancel()
        self._debounce_task = asyncio.create_task(self._debounced_search(query))

    async def _debounced_search(self, query: str) -> None:
        await asyncio.sleep(0.1)  # 100ms debounce
        if query == self._pending_query and len(query) >= 2:
            results = self.search_service.fuzzy_search(query)
            self.results_widget.update_results(results)
```

## Tests

`tests/tui/test_insert_mode.py`:
- `test_o_opens_new_line` — pressing 'o' in NORMAL creates new line and enters INSERT
- `test_O_opens_line_above` — 'O' inserts above cursor
- `test_insert_card_selection` — select card from search results, verify buffer updated
- `test_quantity_prefix` — type "4" then select card → "4 CardName"
- `test_escape_cancels_insert` — Escape exits INSERT, removes empty line if nothing typed
- `test_search_debounce` — typing fast doesn't trigger search per keystroke

`tests/editor/test_operators.py`:
- `test_increment_quantity` — 4 → 5
- `test_decrement_quantity` — 4 → 3
- `test_decrement_to_zero_deletes` — 1 → line removed
- `test_increment_on_comment_noop` — no change on comment line
- `test_set_quantity` — set to specific value

## IMPORTANT

- Search results use the SAME text-column format as the deck view — visual cohesion
- Inline expansion in search results uses the same format as deck view expansion
- The search overlay is the primary way to add cards — it must feel fast and responsive
- 100ms debounce prevents janky re-rendering while typing
- Insert mode should feel purposeful for deck editing, not like a generic text editor
- Quantity editing (+/-) in NORMAL mode is a deck-specific power feature

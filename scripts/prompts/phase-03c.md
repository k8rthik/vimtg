You are building vimtg — a TUI-based MTG deck builder. This is Phase 3c: TUI widgets, MainScreen, and VimTGApp.

Read `PROGRESS.md` and existing source files for context. Phase 3a created Buffer/Cursor/Motions, Phase 3b created ModeManager and KeyMap.

This is where the text-first vision comes to life. The UI is text columns with inline card expansion — NOT panels/sidebars.

## Design Reference

The deck view renders as aligned text columns:
```
  Qty  Card                    Mana    Type
  ─────────────────────────────────────────────
  // Creatures
  4    Goblin Guide            {R}     Creature
  4    Monastery Swiftspear    {R}     Creature
> 4    Lightning Bolt          {R}     Instant
  │    Instant
  │    Lightning Bolt deals 3 damage to any target.
  │    Set: STA  Rarity: Uncommon  Price: $1.50
  4    Lava Spike              {R}     Sorcery
  ─────────────────────────────────────────────
  -- NORMAL --  burn.deck [+]  40 cards  Ln 5/15
```

## 1. DeckView Widget — `src/vimtg/tui/widgets/deck_view.py`

The primary visual component. Custom Textual widget that renders the Buffer.

```python
class DeckView(Static):
    """Renders a deck Buffer as text columns with syntax highlighting and inline expansion."""

    buffer: reactive[Buffer]
    cursor: reactive[Cursor]
    expanded_line: reactive[int | None]  # Currently expanded card line
    resolved_cards: reactive[dict[str, Card]]  # Card data for expansion

    def __init__(self, buffer: Buffer, cursor: Cursor) -> None: ...

    def render(self) -> RenderableType:
        """Render the full deck view with Rich markup."""

    def _render_line(self, line_idx: int, buf_line: BufferLine) -> str:
        """Render a single line with column alignment and syntax highlighting.

        Collapsed card line:
          [dim]4[/]    [white]Lightning Bolt[/]          [red]{R}[/]     [dim]Instant[/]

        Comment line:
          [dim italic]// Creatures[/]

        Sideboard line:
          [yellow]SB:[/]  [dim]2[/]    [white]Rest in Peace[/]        [dim]{1}{W}[/]  [dim]Enchantment[/]
        """

    def _render_expansion(self, card: Card) -> list[str]:
        """Render inline expansion lines for a card.

        │    Instant
        │    Lightning Bolt deals 3 damage to any target.
        │    Set: STA  Rarity: Uncommon  Price: $1.50
        """

    def _format_mana(self, mana_cost: str) -> str:
        """Format mana symbols with color: {R} → [red]{R}[/], {U} → [blue]{U}[/], etc."""

    def scroll_to_cursor(self) -> None:
        """Ensure cursor line is visible in viewport."""
```

### Rendering rules

1. **Cursor line** (`>`): highlighted background, bold text
2. **Card lines**: aligned columns — Qty (3 chars), Card Name (24 chars), Mana (7 chars), Type (rest)
3. **Comment lines**: dim italic, full width
4. **Section headers** (`// Creatures`): dim italic, slightly brighter than regular comments
5. **Blank lines**: empty row (preserves visual grouping)
6. **Sideboard prefix**: `SB:` in yellow
7. **Expanded card**: indented with `│` prefix, dim text. Shows oracle_text, type_line, set/rarity/price
8. **Column widths**: auto-calculated based on terminal width. Name column gets flex space.

### Inline expansion

When `cursor.row` is on a card line and that card is in `resolved_cards`:
- Render 2-4 expansion lines immediately below the cursor line
- Expansion lines use `│` prefix and dim styling
- Line 1: Full type line
- Line 2: Oracle text (wrap if long)
- Line 3: Set, Rarity, Price (if available)
- P/T on line 1 for creatures: `Creature — Goblin Scout  2/2`

Expansion follows cursor — as j/k moves, expansion moves with it.

## 2. StatusLine Widget — `src/vimtg/tui/widgets/status_line.py`

```python
class StatusLine(Static):
    """Bottom status bar showing mode, file info, and position."""

    mode: reactive[Mode]
    filename: reactive[str]
    modified: reactive[bool]
    card_count: reactive[int]
    cursor_pos: reactive[tuple[int, int]]
    total_lines: reactive[int]

    def render(self) -> RenderableType:
        """Render status line:
        -- NORMAL --  burn.deck [+]  40 cards  Ln 5/15
        Mode colors: NORMAL=green, INSERT=blue, VISUAL=orange, COMMAND=yellow
        """
```

## 3. CommandLine Widget — `src/vimtg/tui/widgets/command_line.py`

```python
class CommandLine(Static):
    """Command input at bottom of screen. Shows when in COMMAND or SEARCH mode."""

    visible: reactive[bool]
    prefix: reactive[str]  # ":" or "/"
    text: reactive[str]
    message: reactive[str]  # Feedback messages (e.g., "written burn.deck")

    def render(self) -> RenderableType: ...

    def handle_key(self, key: str) -> str | None:
        """Process keystrokes in command mode.
        Returns command string on Enter, None otherwise."""

    def show(self, prefix: str) -> None: ...
    def hide(self) -> None: ...
    def set_message(self, msg: str) -> None:
        """Show a temporary feedback message (vim-style, bottom line)."""
```

## 4. MainScreen — `src/vimtg/tui/screens/main_screen.py`

```python
class MainScreen(Screen):
    """Primary editing screen. Composes DeckView + StatusLine + CommandLine."""

    BINDINGS = []  # We handle keys manually via KeyMap

    def compose(self) -> ComposeResult:
        yield DeckView(...)
        yield StatusLine(...)
        yield CommandLine(...)

    def on_key(self, event: Key) -> None:
        """Route ALL key events through the vim KeyMap.
        Prevent Textual's default key handling — we own the keys."""

    def _handle_normal_action(self, action: ParsedAction) -> None:
        """Dispatch NORMAL mode actions: motions, operators, mode switches."""

    def _handle_insert_action(self, action: ParsedAction) -> None: ...
    def _handle_command_action(self, action: ParsedAction) -> None: ...
```

### Key routing

The MainScreen intercepts ALL key events via `on_key` and routes them through the KeyMap:

1. `event.prevent_default()` — prevent Textual from handling the key
2. Feed key to `KeyMap.feed(key_name)`
3. If COMPLETE → dispatch action based on action_type
4. If PENDING → do nothing (wait for more keys)
5. If NO_MATCH → ignore

Action dispatch:
- `motion` → execute motion function, update cursor
- `mode_switch` → transition mode via ModeManager
- `operator` → execute operator (placeholder for Phase 5)
- `command` → submit to command handler (placeholder for Phase 5)
- `special` → handle undo, redo, increment, decrement, etc.

## 5. VimTGApp — `src/vimtg/tui/app.py`

```python
class VimTGApp(App):
    """Main Textual application."""

    CSS = """
    Screen {
        layout: vertical;
    }
    DeckView {
        height: 1fr;
    }
    StatusLine {
        height: 1;
        dock: bottom;
    }
    CommandLine {
        height: 1;
        dock: bottom;
    }
    """

    def __init__(self, deck_path: Path | None = None) -> None: ...

    def on_mount(self) -> None:
        """Load deck file, initialize services, push MainScreen."""

    def action_quit(self) -> None: ...
```

## 6. Theme — `src/vimtg/tui/theme.py`

```python
# Color constants for consistent vim-like dark theme
COLORS = {
    "bg": "#1e1e2e",
    "fg": "#cdd6f4",
    "cursor_bg": "#313244",
    "comment": "#6c7086",
    "section_header": "#89b4fa",
    "card_name": "#cdd6f4",
    "quantity": "#fab387",
    "mana_white": "#f5e0dc",
    "mana_blue": "#89b4fa",
    "mana_black": "#a6adc8",
    "mana_red": "#f38ba8",
    "mana_green": "#a6e3a1",
    "mana_colorless": "#9399b2",
    "sideboard_prefix": "#f9e2af",
    "expansion_border": "#45475a",
    "expansion_text": "#a6adc8",
    "mode_normal": "#a6e3a1",
    "mode_insert": "#89b4fa",
    "mode_visual": "#fab387",
    "mode_command": "#f9e2af",
}
```

## 7. CLI integration — extend `src/vimtg/cli.py`

```python
@main.command()
@click.argument("path", type=click.Path(), required=False)
def edit(path: str | None = None) -> None:
    """Open deck in TUI editor."""
    app = VimTGApp(deck_path=Path(path) if path else None)
    app.run()
```

Make `edit` the default command when no subcommand is given.

## Tests

`tests/tui/test_widgets.py`:
- `test_deck_view_renders` — DeckView produces non-empty output
- `test_deck_view_cursor_highlight` — cursor line has different rendering
- `test_status_line_mode_display` — shows current mode name
- `test_command_line_hidden_by_default` — not visible in NORMAL
- `test_mana_format` — {R} renders with color markup

`tests/tui/test_app.py`:
- `test_app_starts` — VimTGApp mounts without error (use `app.run_test()`)
- `test_app_loads_deck` — opens with a deck file loaded
- `test_key_j_moves_down` — pressing j moves cursor down
- `test_key_k_moves_up` — pressing k moves cursor up
- `test_key_gg_goes_to_top` — gg goes to first line
- `test_key_colon_enters_command` — : switches to COMMAND mode

Use Textual's `async with app.run_test() as pilot:` pattern for TUI tests.

## IMPORTANT

- The DeckView is TEXT COLUMNS — not a DataTable widget. We render it ourselves with Rich markup for full control over alignment, coloring, and inline expansion.
- Inline expansion follows cursor automatically — no toggle needed
- Prevent Textual's default key handling — we own ALL keys in NORMAL mode
- The theme uses a Catppuccin Mocha-inspired dark palette — fits the terminal aesthetic
- Mana symbols get color-coded: {R}=red, {U}=blue, {B}=gray, {W}=pink, {G}=green
- Keep files under 200 lines. Split DeckView rendering logic into a separate `deck_renderer.py` if needed.

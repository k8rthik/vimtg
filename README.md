<p align="center">
<pre align="center">
       _           _
__   _(_)_ __ ___ | |_ __ _
\ \ / / | '_ ` _ \| __/ _` |
 \ V /| | | | | | | || (_| |
  \_/ |_|_| |_| |_|\__\__, |
                       |___/
</pre>
</p>

<h3 align="center">Vim-powered Magic: The Gathering deck builder for the terminal</h3>

<p align="center">
<code>hjkl</code> to navigate &middot; <code>dd</code> to delete &middot; <code>/</code> to search &middot; <code>:wq</code> to save &middot; plain text decks that live in git
</p>

---

Your decks are just text files. Your editor speaks vim. Your card database is local — 30,000+ cards searchable in milliseconds, no internet required after the first sync. Mana costs render in color. Card details expand inline. Undo branches let you explore different builds without losing anything.

Built with [Textual](https://textual.textualize.io). Styled in [Catppuccin Mocha](https://github.com/catppuccin/catppuccin). Designed for people who think in keystrokes.

## Quick start

```bash
git clone https://github.com/k8rthik/vimtg.git
cd vimtg
pip install -e .

vimtg sync               # download card database (~35 MB, one-time)
vimtg edit burn.deck      # open a deck
vimtg                     # or launch the greeter
```

## The `.deck` format

Plain text. Git-friendly. Readable without tooling.

```
// Deck: Burn
// Format: modern

// Creature
4 Goblin Guide
4 Monastery Swiftspear
4 Eidolon of the Great Revel

// Instant
4 Lightning Bolt
4 Searing Blaze
4 Skullcrack
4 Boros Charm

// Land
4 Inspiring Vantage
4 Sacred Foundry
8 Mountain

// Sideboard
SB: 2 Rest in Peace
SB: 3 Kor Firewalker
SB: 2 Smash to Smithereens
```

Sections are comments. Sideboard lines start with `SB:`. Metadata goes at the top. That's the whole spec.

## Features

**Vim, for real** — Normal, Insert, Visual, Command modes. Motions (`w`, `b`, `{`, `}`), operators (`d`, `y`, `c`), text objects, dot repeat, macros, named registers. If your fingers know vim, they know vimtg.

**Offline card search** — Type `o` to open insert mode and start searching. Fuzzy matching against a local SQLite FTS5 index. Card details, oracle text, and prices shown inline as you browse results.

**Tags** — Annotate cards with `#core`, `#flex`, `#budget`, whatever you want. Filter your view with `:filter core+flex`, jump between tagged cards with `tn`/`tp`, rename tags across the deck with `:retag`.

**Undo tree** — Not just linear undo. Branch your history, name checkpoints, switch between build iterations. `u` to undo, `Ctrl-R` to redo, `:checkpoint` and `:branch` for the rest.

**Bulk operations** — `:g/Creature/d` deletes every creature. `:%s/Bolt/Helix/g` substitutes across the whole deck. `:sort cmc` reorders by mana cost. Power tools for power users.

**Import / Export** — `:export arena`, `:export mtgo`, `:export moxfield`, `:export archidekt`. Import auto-detects format.

**Deck analytics** — `:stats` shows mana curve, type breakdown, color distribution, and total price. `:validate` checks 60-card minimum, 4-of rule, and sideboard limits.

## Keybindings

<details>
<summary><strong>Navigation</strong></summary>

| Key | Action |
|-----|--------|
| `j` / `k` | Move down / up |
| `gg` / `G` | First / last line |
| `w` / `b` | Next / prev card |
| `{` / `}` | Next / prev section |
| `Ctrl-D` / `Ctrl-U` | Half page down / up |

</details>

<details>
<summary><strong>Editing</strong></summary>

| Key | Action |
|-----|--------|
| `o` / `O` | Add card below / above (opens search) |
| `i` | Edit current line |
| `dd` | Delete card |
| `yy` | Yank (copy) card |
| `p` / `P` | Paste below / above |
| `+` / `-` | Increment / decrement quantity |
| `.` | Repeat last change |
| `u` / `Ctrl-R` | Undo / redo |

</details>

<details>
<summary><strong>Visual mode</strong></summary>

| Key | Action |
|-----|--------|
| `v` / `V` | Visual / visual-line |
| `d` / `y` | Delete / yank selection |
| `Escape` | Exit visual mode |

</details>

<details>
<summary><strong>Tags</strong></summary>

| Key | Action |
|-----|--------|
| `ta` | Add tag |
| `tr` | Remove tag |
| `tt` | Toggle tag |
| `tf` | Filter by tag expression |
| `tl` | List all tags |
| `tc` | Clear tags |
| `tn` / `tp` | Next / prev tagged card |

</details>

## Commands

Type `:` to enter command mode. Tab-completion is built in.

<details>
<summary><strong>Full command reference</strong></summary>

| Command | Description |
|---------|-------------|
| `:w` | Save deck |
| `:q` | Quit (`:q!` to force) |
| `:wq` | Save and quit |
| `:sort [field]` | Sort by name, cmc, type, color, qty, or tag |
| `:%s/old/new/g` | Substitute across deck |
| `:g/pattern/d` | Delete matching cards |
| `:find pattern` | Jump to matching card |
| `:tag name` | Add tag (`:5,10tag` for range) |
| `:untag name` | Remove tag (`:untag!` clears all) |
| `:tags` | List tags with counts |
| `:filter expr` | Filter by tag (`+` AND, `\|` OR, `-` NOT) |
| `:retag /old/new/` | Rename tag across deck |
| `:export fmt` | Export to arena, mtgo, moxfield, or archidekt |
| `:import file` | Import deck (auto-detects format) |
| `:stats` | Mana curve, type breakdown, price totals |
| `:validate` | Check deck legality |
| `:checkpoint name` | Tag a point in undo history |
| `:branch [name]` | Create, list, or switch undo branches |
| `:config` | Settings menu |
| `:help [cmd]` | Help |

</details>

## CLI

```bash
vimtg                             # greeter screen
vimtg edit [file]                 # open editor
vimtg new "Deck Name" -f modern   # create new deck
vimtg sync                        # download/update card database
vimtg search "lightning bolt"     # search cards
vimtg validate deck.deck          # check legality
vimtg info deck.deck              # deck summary
vimtg convert in.mtgo --to arena -o out.txt
```

## Architecture

```
src/vimtg/
  domain/        Pure data — Card, Deck, Tags (frozen dataclasses, no I/O)
  editor/        Vim engine — Buffer, Cursor, Motions, Operators, Keymap
    command_handlers/   One module per command family
  data/          SQLite + FTS5 search, Scryfall sync, deck file I/O
  tui/           Textual rendering layer — no business logic
    widgets/     CommandLine, SearchResults, WhichKey, HelpPanel
    screens/     MainScreen, Greeter
```

The editor has zero dependency on Textual. The TUI translates key events into editor calls and renders the result. Everything interesting is testable without a terminal.

## Tech stack

| | |
|:--|:--|
| **Python** | 3.12+, strict mypy |
| **TUI** | Textual + Rich |
| **CLI** | Click |
| **Search** | SQLite FTS5 |
| **Cards** | Scryfall bulk data (offline) |
| **Theme** | Catppuccin Mocha |
| **Build** | Hatchling |
| **Tests** | pytest |
| **Lint** | Ruff |

## License

MIT

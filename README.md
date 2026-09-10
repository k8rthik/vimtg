```
         _           _
  __   _(_)_ __ ___ | |_ __ _
  \ \ / / | '_ ` _ \| __/ _` |
   \ V /| | | | | | | || (_| |
    \_/ |_|_| |_| |_|\__\__, |
                         |___/
```

**Vim-powered Magic: The Gathering deck builder for the terminal.**

`hjkl` to navigate · `dd` to delete · `o` to add a card · `:wq` to save · plain text decks that live in git

---

Your decks are plain text files. Your editor speaks vim. Your card database is local: 30,000+ Scryfall cards searchable in milliseconds, no internet required after the first sync. Mana costs render in color, card details expand inline under the cursor, legality problems show up as gutter signs while you type, and a git-like history with branches, merges, and rebases lives alongside every deck.

Built with [Textual](https://textual.textualize.io). Styled in [Catppuccin Mocha](https://github.com/catppuccin/catppuccin). Designed for people who think in keystrokes.

## Contents

- [Quick start](#quick-start)
- [Project status](#project-status)
- [The `.deck` format](#the-deck-format)
- [Feature rundown](#feature-rundown)
  - [Vim editing engine](#vim-editing-engine)
  - [Card database and search](#card-database-and-search)
  - [Adding cards](#adding-cards)
  - [Zones](#zones)
  - [Sections, layouts, and placement](#sections-layouts-and-placement)
  - [Categories](#categories)
  - [Tags and filters](#tags-and-filters)
  - [Bulk editing](#bulk-editing)
  - [Format-aware validation and live lint](#format-aware-validation-and-live-lint)
  - [Sideboard plans](#sideboard-plans)
  - [Analytics](#analytics)
  - [Split panes and EDHREC](#split-panes-and-edhrec)
  - [Import, export, and clipboard](#import-export-and-clipboard)
  - [Version control](#version-control)
  - [Greeter](#greeter)
  - [Configuration](#configuration)
  - [Help](#help)
- [Keybindings](#keybindings)
- [Commands](#commands)
- [CLI](#cli)
- [Architecture](#architecture)
- [Known gaps](#known-gaps)
- [Development](#development)

## Quick start

```bash
git clone https://github.com/k8rthik/vimtg.git
cd vimtg
pip install -e .

vimtg sync                # download the card database (~25 MB); the TUI also
                          # auto-syncs in the background when data is stale
vimtg burn.deck           # open a deck, vim-style (`vimtg edit burn.deck` also works)
vimtg                     # or launch the greeter
```

Requires Python 3.12+. No API keys are needed for anything: Scryfall bulk data, EDHREC, and every deck-site importer use public endpoints.

## Project status

Surveyed 2026-09-09 on `main`.

| | |
|:--|:--|
| Source | ~21,000 lines across 117 modules (`src/vimtg/`) |
| Tests | 2,625 passing (139 files, ~25,800 lines), 94% line coverage; CI runs on Python 3.12 and 3.13 |
| Lint / types | `ruff check` clean; `mypy --strict` clean on all 117 source files |
| Git | 118 commits; tags `v0.5.0` through `v0.8.0` |
| Package version | `pyproject.toml` and `vimtg.__version__` still declare `0.1.0` |

The original ten-phase build (scaffold through packaging) is complete. Work since then has added zones and zone blocks, categories, a persistent VCS with a floating lazygit-style history overlay, interactive merge resolution, split panes, EDHREC recommendations, a live analytics pane, URL importers for six deck sites, sideboard plans, format-aware lint, header counts, and mouse-wheel scrolling. The docs in `docs/` are current with the latest commit. The newest addition is the floating history overlay (`gh`).

## The `.deck` format

Plain text. Git-friendly. Readable without tooling. The parser is intentionally permissive: it accepts more than it writes.

```
// Deck: Spellementals
// Format: standard
// Author: keerthik
// Tags: aggro, prowess

DCK:

    // Creatures
    4 Hearth Elemental // Stoke Genius  @threats
    4 Eddymurk Crab  @threats  #core
    4 Sunderflock  @threats  // primary win-con

    // Instants
    4 Opt  @cantrips  #core
    3 Spell Pierce  @interaction
    2 Burst Lightning  @interaction

    // Lands
    5 Island
    4 Steam Vents

SB:
    2 Annul
    1 Negate
    2 Broadside Barrage

MB: 2 Ral, Crackling Wit  // try after rotation

VS: 4c Control  // grind plan
    -2 Burst Lightning
    -1 Sunderflock
    +1 Spell Pierce
    +2 Negate
```

| Line kind | Shape | Notes |
|---|---|---|
| Metadata | `// Key: value` | Keys: `Deck`, `Format`, `Author`, `Description`, `Source`, `Tags`. Values may be empty. Unknown keys are preserved. |
| Zone block header | `DCK:` / `SB:` / `MB:` / `CMD:` / `CMP:` alone on a line | Python-style: indented lines below belong to the zone, a blank line is neutral, any unindented line closes the block. This is the default style for new decks. |
| Zone prefix | `SB: 2 Rest in Peace` | Per-line prefix. An explicit prefix always wins over the enclosing block. |
| Section header | `// Creatures`, `// @ramp`, `// Sideboard` | Type headers accept singular or plural in any case. Category headers use `@`. |
| Card entry | `N Name  @category  #tag #tag  // comment` | Quantity defaults to 1. Two-space delimiters keep double-faced names like `Fire // Ice` unambiguous. |
| Plan header | `VS: Matchup  // note` | Starts a sideboard plan block. |
| Plan entry | `-N Card` / `+N Card` | Indented under `VS:`. Never counted as deck cards. |
| Comment | any other `// text` | Freeform, preserved. |

Zones: `DCK` mainboard (implicit when no prefix or block applies), `SB` sideboard, `MB` maybeboard (a scratchpad never counted toward size or copy limits), `CMD` command zone (up to two partners, quantity 1), `CMP` companion (one, quantity 1, must actually have the Companion ability).

Header counts such as `// Creatures (12)`, `DCK: (60)`, `// Deck: Burn · 60/15 cards`, and `VS: Tron (-4 +4)` are rendered in the editor and never written to disk.

Full spec: [docs/deck-format.md](docs/deck-format.md).

## Feature rundown

### Vim editing engine

The editor engine has no dependency on Textual. Keys flow through a translator, a macro recorder, a remapper, a key-sequence parser, and then a session handler, so everything below is testable headlessly.

- **Modes**: Normal, Insert, Visual, Visual-line, Command, Search. Insert has four submodes: card search (`o`/`O`/`c`), line edit (`i`), tag input (`t` keys and `gc`), and comment input (`A`). `Escape` always returns to Normal.
- **Motions**: `j`/`k` (skip blank lines), `w`/`b` (next/previous card), `{`/`}` (previous/next section), `[[`/`]]` (previous/next section or plan header), `gg`/`G`, `{count}G` (go to line), `Ctrl-D`/`Ctrl-U` (half page). Any motion takes a count.
- **Operators**: `d`, `y`, `c` compose with motions and double up as `dd`, `yy`, `cc`. Counts multiply (`2d3j` is six lines). `dj`/`dk` use raw line arithmetic so a delete never spills across a section boundary. `c` deletes and opens card search. `x` deletes the card under the cursor. `p`/`P` put below/above; `3p` puts three copies.
- **Quantity**: `+`/`-` adjust the count (`10+`, `3-`). `-` at zero deletes the line. Both preserve zone prefixes, plan signs, `@category`, `#tags`, and comments.
- **Line editing**: `i` edits the current line in place. On a `// Key:` metadata line the prefix is locked and only the value is editable. On `// Format:` the value ghost-completes from the known formats and warns when you confirm an unknown one. `A` adds or edits the card's inline comment.
- **Visual mode**: `v`/`V` select, `d`/`y`/`c` act on the range, `o` swaps the selection ends. Category and tag prompts honour the visual range.
- **Registers**: `"a`–`"z` named, `"A`–`"Z` append, unnamed, yank register `0`, delete history shifted through `1`–`9`.
- **Marks**: `m{a-z}` set, `'{a-z}` jump, all 26 letters. Marks shift correctly through inserts, deletes, puts, and zone moves.
- **Macros**: `q{a-z}` record, `q` stop, `@{a-z}` play, `@@` replay last, `3@a` plays three times. Playback re-feeds keys through the full pipeline.
- **Dot repeat**: `.` replays the last operator, quantity, zone, or board action; a count on `.` overrides the recorded one.
- **Undo/redo**: `u`/`Ctrl-R`, counted. Session history is a snapshot tree: undo walks to the parent, redo to the newest child, and abandoned branches are kept. Rapid same-description edits within two seconds collapse into one step.
- **Remapping**: `:map key action` (session-only, multi-character targets allowed, `:`-prefixed targets auto-submit), `:unmap key`, bare `:map` lists. Persistent maps live in `[keybindings]` in `config.toml`, per mode.
- **Which-key**: when a key sequence is pending (`d`, `y`, `c`, `g`, `[`, `]`, `"`, `q`, `@`, `m`, `'`, `S`, `t`, `z`) a popup shows the possible completions, derived from the same key spec as the help overview. The status line shows the pending sequence and counts.
- **Mouse**: wheel and trackpad scroll the deck view, the split pane, the EDHREC pane, and the analytics pane, vim-style: three lines per notch, the cursor is dragged only when it would leave the scroll-off band. There is no click-to-position.

### Card database and search

- **Offline Scryfall data**: `vimtg sync` downloads the `oracle_cards` bulk file, streams it into SQLite, and builds an FTS5 index over name, type line, and oracle text. Tokens, emblems, and art-series cards are skipped. Downloads are content-length checked and written atomically; a corrupt cache is deleted and reported.
- **Auto-sync**: the TUI checks on launch and hourly, and syncs on a worker thread when the database is missing or older than seven days. A toast reports success or failure, and search and lint light up retroactively once data arrives. Disable with `:set noautosync` or the `VIMTG_NO_AUTOSYNC` environment variable.
- **Query syntax**: plain words do FTS5 prefix matching. Scryfall-style filters are recognised: `t:`/`type:`, `o:`/`oracle:` (quoted phrases allowed), `cmc=N`, `cmc<=N`, `cmc>=N`, `set:`, `r:`/`rarity:`, `c:`/`color:` (see [Known gaps](#known-gaps) for the colour filter).
- **Format filtering**: in the editor, search results are filtered to cards legal or restricted in the deck's declared format when that format is known.
- **Card model**: name, mana cost, CMC, type line, oracle text, colours, colour identity, P/T, set, rarity, five price sources (USD, USD foil, EUR, EUR foil, tix), legalities, layout, keywords. Transform and modal DFCs use the front face; split and adventure cards join both faces.

### Adding cards

- `o`/`O` open a search prompt below/above the cursor. A count sets copies: `4o` adds four of the confirmed card.
- Results update from two characters on a worker thread, up to `search_limit`. The overlay shows up to ten rows with name, colourised mana cost, type line, and price, plus a one-line oracle preview for the selected row. The top match becomes a ghost in the command line.
- `Tab`/`Ctrl-J`/`Ctrl-N`/`Down` next, `Shift-Tab`/`Ctrl-K`/`Ctrl-P`/`Up` previous, `Enter` confirms, `Escape` discards the scratch line and restores the cursor.
- Confirming a card already in the same zone bumps its quantity instead of adding a line.
- The new card follows the cursor's zone. Inside a `SB:`/`CMD:` block it lands there in matching style. In the mainboard it is filed by the placement policy (see below). Inside a `VS:` block the search runs against the deck's own cards and writes a signed plan line.
- **Inline expansion**: with `auto_expand` on, the cursor's card renders a detail block under it: type line and P/T, word-wrapped oracle text, set, rarity, and price. The deck view windows by rendered rows so the expansion never clips.

### Zones

`zs` / `zm` / `zd` / `zc` / `zp` move the cursor card to the **s**ideboard, **m**aybeboard, main **d**eck, **c**ommander zone, or com**p**anion slot. The bare key moves all copies; `2zs` splits two off. Moving into a zone that already holds the card merges quantities and unions tags. Category, tags, and comments travel with the card. A move that creates a brand-new zone opens it as an indented block; moves into existing zones match the style already in use.

### Sections, layouts, and placement

- **Section model**: every header has one identity, so `// Sorcery` and `// Sorceries` are the same section. Section cleanup merges duplicates, drops derived headers with no cards, collapses blank runs, and pads one blank line before each header. Bare zone headers such as `DCK:` are structural and never removed.
- **Layouts**: `gl` or `:layout` rewrites the mainboard grouped by card type (`// Creatures`, `// Instants`, ...) or by category (`// @ramp`, ...). Each card keeps its `@category` token, so toggling is lossless. The rewrite is an undoable edit, zones keep their block or prefix style, and `VS:` blocks are carried over verbatim.
- **Placement**: with `auto_sort` on, a new card is filed by its primary type in a type layout (unknown types go to `// Other`) or by its category in a category layout (falling back to the header it was opened under, then `// Uncategorized`). With `auto_sort` off it stays where the line was opened and inherits the enclosing category header. `zd` into a category deck lands in the card's own category section.
- **In-group order** follows the `sort_order` setting (mana value by default).

### Categories

One `@category` purpose label per card (`@ramp`, `@draw`, `@wincon`); names are 1–32 chars of letters, digits, and hyphens.

- `gc` prompts and sets on the current card or visual range; `gC` clears. The prompt ghost-completes from the deck's own categories, then a cross-deck history file, then sixteen presets. `Tab` accepts.
- In a category-grouped deck the token and the header always agree: setting a category moves the card under its `// @name` header (created if needed), clearing moves it to `// Uncategorized`, and a card added under a category header takes that category.
- `:cat name` / `:cat!` (range-aware), `:categories` lists with counts.
- Archidekt imports turn user-made categories into `@category` tokens.

### Tags and filters

Deck-level annotations, any number per card: `#core`, `#flex`, `#budget`.

- `ta` add, `tr` remove, `tt` toggle, `tc` clear, `tl` list with counts, `tf` filter, `tn`/`tp` jump to the next/previous card sharing a tag with the cursor.
- `:tag`, `:untag`, `:untag!`, `:tags`, `:retag /old/new/` (rename everywhere), `:dtag` / `:duntag` (deck-level `// Tags:` line).
- **Filter grammar**: `core+flex` is AND, `core|flex` is OR, `-flex` is NOT. `:filter expr` dims non-matching cards and suppresses their expansion; `:filter!` or an empty expression clears.

### Bulk editing

Most commands take a vim range: `%`, `5,10`, `.`, `$`, or a mark pair.

- `:sort [field]` sorts the current section (or range) by `name`, `qty`, `cmc`, `type`, `color`, `tag`, `category`, `power`, `toughness`, `rarity`, or `price`. Entries are sorted within each zone so a range spanning zones never rezones a line. `:sort!` reverses. Missing card data falls back to name order.
- `:s/old/new/[gi]` substitutes literally across the range (`:%s/Bolt/Helix/g`).
- `:g/pattern/d` and `:v/pattern/d` delete matching or non-matching card lines.
- `:find pattern` (also `/`) jumps to the next matching card, case-insensitive regex, wrapping.

### Format-aware validation and live lint

Formats with rules: standard, pioneer, modern, legacy, vintage, pauper, historic, commander, brawl. Legality comes entirely from the synced Scryfall data; there are no hard-coded ban lists.

- **Live gutter signs**: `✗` error and `!` warning in a two-character column. The reason appears in the status line when the cursor is on the line. The status line also totals `✗N` and `!N`.
- **Checks**: invalid quantity, unknown card, unknown format, banned/not-legal/restricted cards (warnings only in the maybeboard), copy limits across main + side + command zone with basic lands exempt, minimum or exact deck size, sideboard allowed and size, companion count, quantity, and actual Companion ability, commander present, quantity 1, at most two, legendary, partner-pair heuristic, and colour identity of every mainboard card.
- **Plan lint**: an out must be in the mainboard, an in must be in the sideboard, never more copies than the zone holds, a missing sign is an error; unbalanced ins/outs, duplicate plan names, and a card listed twice are warnings.
- `:validate` prints the full list; `vimtg validate deck.deck` does the same from the shell and exits non-zero on errors.

### Sideboard plans

A plan is a `VS: <matchup>` block of `-N Card` (out of the mainboard) and `+N Card` (in from the sideboard) lines, kept at the end of the file.

- `:plan <matchup>` activates a plan, creating its block when new. Bare `:plan` cycles, `:plan!` deactivates, `:plans` lists every plan with `-out +in` totals. `]v`/`[v` jump between plans and activate them. A deck with exactly one plan auto-activates it.
- `zo`/`zi` board the cursor card out/in of the active plan (all copies, or `2zo` for two), clamped to what the zone holds; entries are removed at zero.
- The deck view shows each card's `-N`/`+N` delta for the active plan, plan headers show `(-4 +4)` with `!` when unbalanced, and the status line shows `vs Tron -4/+4`.
- Inside a plan block, `o` searches the deck's own cards, `+`/`-` adjust counts, and `dd` removes an entry.
- `:export guide` and `vimtg guide --markdown` write the plans as a Markdown sideboard guide.

### Analytics

- `:stats` toggles a summary of the mana curve, type breakdown, colour pips, and total price.
- `:analytics` (or `Sa`) opens a live pane that recomputes on every edit: **curve** bar chart (0 to 7+), **types**, **zones**, **categories** (when used), **mana base** with per-colour pips, sources versus needed (Karsten-style requirement scaled to deck size) and a `✓`/`✗ need N more` verdict, and **draws**: exact hypergeometric odds of two lands in the opener, three land drops by turn 3, and a cursor-following line giving the opener and by-turn-3 odds for the card under the cursor. With a plan active the whole pane shows the post-board deck.
- `vimtg info deck.deck` prints counts from the shell.

### Split panes and EDHREC

One pane at a time, beside (`Sv`, `:vsplit file`) or below (`Sh`, `:split file`) the editor.

- **Deck pane**: another deck file, read-only, for comparing a netdeck or an old version. `j`/`k`, `Ctrl-D`/`Ctrl-U`, `g`/`G` scroll.
- **EDHREC pane** (`Sr`, `:edhrec [type]`): recommendations for the commander(s) on the deck's `CMD:` lines, Commander-only, partner pairs supported. Tabs: Top, Creatures, Instants, Sorceries, Artifacts, Enchantments, Planeswalkers, Battles, Lands. Each row shows inclusion rate and synergy score; `✓` marks cards already in the deck. `h`/`l` switch tabs, `Enter` adds the selected card to its type section. Responses are cached for seven days in the XDG cache directory. `VIMTG_NO_EDHREC` disables lookups.
- **Analytics pane** (`Sa`, `:analytics`): described above; opens unfocused because it is a readout.
- `Ss` switches focus, `Sc` or `:close` closes. A focused pane has an orange border. Any editing key falls through to the editor and refocuses it.

### Import, export, and clipboard

- **Formats**: vimtg, MTGO text, MTGO `.dek` XML, Arena, Moxfield CSV, Archidekt CSV, and a Markdown sideboard guide (export only). `:import file` auto-detects the format; `:export fmt [file]` writes it. `vimtg convert` does the same from the shell.
- **URL import** from Moxfield, Archidekt, ManaBox, Deckstats, TappedOut, and MTGGoldfish via `:import <url>` or the greeter's `[i]` prompt. Commanders, companions, sideboards, and maybeboards map to the right zones; the deck title lands in `// Deck:` and the URL in `// Source:`. No API keys needed.
- **Clipboard**: `:clipboard [fmt]` copies the deck (Arena by default) through an OSC52 escape sequence, so it works over SSH in iTerm2, kitty, Alacritty, WezTerm, and Windows Terminal.
- Export quirks worth knowing: MTGO text and `.dek` park commander and companion cards in the sideboard so they are not lost; Arena export appends `(SET) 0` when a card resolves; Archidekt export skips the maybeboard.

### Version control

Two layers, both stored in the local SQLite database and keyed by deck path.

- **Session undo tree**: `u`/`Ctrl-R` as described above.
- **Persistent VCS**: `:commit "msg"` snapshots the deck (deduplicated by content hash), `:checkpoint name` commits and tags, `:branch` lists, `:branch name` creates, `:branch! name` switches (HEAD persists across sessions), `:merge branch` does a three-way merge with fast-forward detection, `:merge other.deck` merges another file's cards against an empty base, `:rebase branch` replays this branch's commits onto another tip with a replayed-change-wins policy. `:w` auto-snapshots when `auto_snapshot` is on.
- **History overlay** (`gh`, `:history`, `:log`): a floating lazygit-style window over the editor, lazy.nvim style, with the editor dimmed behind it. Panels: Working copy (uncommitted changes against the tip, `c` commits), Branches, Snapshots (7-char id, timestamp, `⇄ merge` marker, `[branch]` for merged-in commits, tags, description), Diff (added, removed, quantity changed, section moved, grouped by zone), and Stats delta (card count, average CMC, price in your configured currency, per-bucket curve delta). Keys: `1`–`5` or `Tab` to pick a panel, `j`/`k`, `gg`/`G`, `Ctrl-D`/`Ctrl-U` or the wheel to move or scroll, `Enter` to open the item, `c` commit, `b` new branch, `B`/`D`/`m`/`r` switch/delete/merge/rebase from the Branches panel, `t`/`T` tag/untag, `R` restore, `p` cherry-pick, `d` toggle unchanged cards, `q`/`Escape`/`gh` close. Merge, rebase, switch, and cherry-pick update the editor in place, keeping the cursor row.
- **Merge screen**: when both sides changed the same card differently, a table of Card / Base / Ours / Theirs / Chosen opens. `o` take ours, `t` take theirs, `c` custom quantity (0 omits), `u` unresolve, `Enter` confirm, `q` abort with a confirmation message. Nothing is committed until you confirm. Merge and rebase results are normalised on write: sections regrouped, freeform comments dropped.

### Greeter

`vimtg` with no arguments opens a greeter with the logo, version, and the five most recent `.deck` files in the current directory. Keys: `n` new deck, `e` file browser, `i` import from a file path or deck URL (bracketed paste supported), `s` sync cards with inline progress, `r` recent files, `1`–`5` open a recent deck, `?` help, `q` quit. `:home` returns here from the editor.

### Configuration

Settings live in `~/.config/vimtg/config.toml` under `[editor]`; malformed values fall back to defaults per field and never block startup. Change them for the session with `:set key=value` (`:set number`, `:set nonumber`, bare `:set` lists all) or persistently in the `:config` screen (`j`/`k`, `h`/`l` cycle, `s` save, `q` close).

| Option | Values | Default | Meaning |
|---|---|---|---|
| `price_source` | usd, usd_foil, eur, eur_foil, tix | usd | Which Scryfall price to show |
| `show_prices` | bool | on | Prices in card views |
| `show_line_numbers` | bool (`number`) | on | Relative line numbers, absolute at the cursor, blank lines skipped |
| `show_which_key` | bool (`whichkey`) | on | Pending-key popup |
| `auto_expand` | bool (`autoexpand`) | on | Card details under the cursor |
| `auto_sort` | bool (`autosort`) | on | File new cards by type or category instead of at the cursor |
| `sort_order` | cmc, name, qty, type, color, tag, category, power, toughness, rarity, price | cmc | Default order for `:sort` and layouts |
| `search_limit` | 10–500 | 50 | Max search results |
| `default_format` | blank, standard, pioneer, modern, legacy, vintage, commander, pauper | blank | Format used when the deck declares none |
| `confirm_quit` | bool (`confirmquit`) | on | Require `:q!` when modified |
| `auto_snapshot` | bool | on | Commit to the VCS on `:w` |
| `auto_sync_cards` | bool (`autosync`) | on | Background card download when missing or stale |
| `theme` | dark | dark | Colour theme (only one exists) |

Where things live (XDG-aware): card database plus snapshots, branches, and HEAD in `~/.local/share/vimtg/cards.db`; config and the category history in `~/.config/vimtg/`; Scryfall bulk files and the EDHREC cache in `~/.cache/vimtg/`. Deck files are ordinary files wherever you keep them; there is no managed deck directory.

### Help

`?` toggles an inline quick-reference panel (scrolls with `j`/`k`, `Ctrl-D`/`Ctrl-U`, `g`/`G`, or the wheel). `F1` or `:help` opens the full-screen help; `:help <command>` opens one of thirty per-command topics. The command line shows cursor-sensitive hints on card lines, plan lines, and elsewhere, and `:` commands fuzzy-complete with `Tab`/`Shift-Tab`.

## Keybindings

Normal mode unless stated. Five rules hold everywhere: one navigation vocabulary (`j`/`k`, `gg`/`G`, `Home`/`End`, `Ctrl-D`/`Ctrl-U`, wheel), one dismissal vocabulary (`q`/`Esc`), one help vocabulary (`?`/`F1`), one job per editor prefix (`g` go, `t` tags, `S` splits, `z` zones, `m` marks), and one key spec that which-key, the help overview, and the drift tests all read. Full reference: [docs/keybindings.md](docs/keybindings.md).

<details>
<summary><strong>Modes and navigation</strong></summary>

| Key | Action |
|-----|--------|
| `i` | Edit current line (value only on metadata lines) |
| `o` / `O` | Add card below / above (`4o` adds four copies) |
| `A` | Add or edit the card's inline comment |
| `:` / `/` | Command line / find |
| `v` / `V` | Visual / visual-line |
| `j` / `k` | Down / up, skipping blanks |
| `w` / `b` | Next / previous card |
| `{` / `}` | Previous / next section |
| `[[` / `]]` | Previous / next section or plan header |
| `[v` / `]v` | Previous / next sideboard plan (activates it) |
| `gg` / `G` / `{n}G` | First / last / nth line |
| `Ctrl-D` / `Ctrl-U` | Half page down / up |
| `m{a-z}` / `'{a-z}` | Set / jump to mark (all 26 letters) |

</details>

<details>
<summary><strong>Editing</strong></summary>

| Key | Action |
|-----|--------|
| `dd` / `yy` / `cc` | Delete / yank / change line |
| `d` `y` `c` + motion | Operators (`dw`, `d}`, `y5G`, ...) |
| `x` | Delete card at cursor |
| `p` / `P` | Paste below / above |
| `+` / `-` | Increment / decrement quantity |
| `zs` `zm` `zd` `zc` `zp` | Move to sideboard / maybeboard / main / commander / companion |
| `zo` / `zi` | Board out of / into the active plan |
| `"{x}` | Use register `x` for the next operator |
| `q{x}` / `@{x}` / `@@` | Record / play / replay macro |
| `.` | Repeat last change |
| `u` / `Ctrl-R` | Undo / redo |

</details>

<details>
<summary><strong>Categories, tags, splits</strong></summary>

| Key | Action |
|-----|--------|
| `gc` / `gC` | Set / clear category (Tab completes) |
| `gl` | Toggle type / category layout |
| `ta` `tr` `tt` `tc` | Add / remove / toggle / clear tags |
| `tf` / `tl` | Filter by expression / list tags |
| `tn` / `tp` | Next / previous card sharing a tag |
| `gh` | Toggle the history overlay |
| `Sv` / `Sh` | Vertical / horizontal split (prompts for a deck) |
| `Sr` / `Sa` | EDHREC pane / analytics pane |
| `Ss` / `Sc` | Switch focus / close pane |
| `?` / `F1` | Quick reference / full help |

</details>

## Commands

Type `:` to enter command mode. Full reference: [docs/commands.md](docs/commands.md).

<details>
<summary><strong>Command reference</strong></summary>

| Command | Description |
|---------|-------------|
| `:w [file]`, `:q`, `:q!`, `:wq`, `:x`, `:e file`, `:home` | File and navigation |
| `:sort [field]`, `:sort!` | Sort section or range |
| `:s/old/new/[gi]` | Substitute (literal) |
| `:g/pat/d`, `:v/pat/d` | Delete matching / non-matching cards |
| `:find pat`, `:search query` | Jump to card / open database search |
| `:cat name`, `:cat!`, `:categories`, `:layout [type\|category]` | Categories and layout |
| `:tag`, `:untag`, `:untag!`, `:tags`, `:filter expr`, `:filter!`, `:retag /a/b/`, `:dtag`, `:duntag` | Tags |
| `:plan [name]`, `:plan!`, `:plans` | Sideboard plans |
| `:export fmt [file]`, `:import file\|url`, `:clipboard [fmt]` | Formats: arena, mtgo, dek, moxfield, archidekt, vimtg, guide |
| `:vsplit`, `:split`, `:close`, `:edhrec [type]`, `:analytics` | Panes |
| `:stats`, `:validate` | Analytics and legality |
| `:history` (or `gh`), `:commit msg`, `:checkpoint name`, `:branch [name]`, `:branch! name`, `:merge target`, `:rebase branch` | Version control |
| `:set [key=value]`, `:config`, `:map`, `:unmap` | Configuration |
| `:help [command]` | Help |

</details>

## CLI

```bash
vimtg                                  # greeter
vimtg burn.deck                        # open a deck (vim-style)
vimtg edit [file]                      # same, explicit
vimtg new "Deck Name" -f commander     # scaffold a new deck in the cwd
vimtg sync [--force]                   # download or refresh the card database
vimtg search "t:creature cmc<=2" -n 40 # search cards
vimtg validate deck.deck               # legality report; exit 1 on errors
vimtg info deck.deck                   # counts summary
vimtg guide deck.deck [--markdown]     # sideboard plans
vimtg convert in.dek --to arena -o out.txt
```

## Architecture

```
src/vimtg/
  domain/      Pure data and rules: Card, Deck, zones, sections, categories,
               tags, sideboard plans, formats, validation, diff, merge,
               analytics, probabilities, snapshot tree (frozen dataclasses, no I/O)
  editor/      Vim engine: buffer, cursor, modes, keymap, motions, operators,
               registers, marks, macros, dot repeat, layout, placement, lint,
               sort, splits, plans, config options, help text
    command_handlers/   One module per ex-command family
  data/        SQLite schema, FTS5 card repository, Scryfall sync, deck file
               parser/serializer, snapshot repository
  services/    Search, deck, import/export, deck-site URL importers, EDHREC,
               history, VCS, diff, clipboard
  config/      XDG paths, config.toml reader/writer, category history
  tui/         Textual layer: app, deck renderer, key translator, theme
    screens/   Main, greeter, help, history, merge, config
    widgets/   Deck view, search results, command line, status line, which-key,
               help panel, analytics, EDHREC, stats, diff, branches, snapshots,
               conflicts, scrolling math
```

The editor and domain layers never import Textual. The TUI translates key events into editor calls and renders the result.

## Known gaps

Found during the survey; none block normal use.

- **Colour search filter is unwired.** `c:r` is parsed but never reaches the SQL, and because a filter routes the query away from FTS you get unfiltered results. Advanced search also hardcodes a limit of 50 and ignores `search_limit`.
- **No text objects, no `n`/`N`, no `H`/`M`/`L`, no till-motion (`t` is the tag prefix).** `h`/`l`/`0`/`$` move a column that nothing renders. `:s` is a literal substitution despite the `/pattern/` syntax.
- **`:g` and `:v` only support `d`** and only see mainboard and sideboard lines.
- **Brawl** has no exact deck size, so a 60-card Brawl deck gets the generic 60-card minimum check.
- **History stats need the card database.** Without a synced database the Stats panel shows no deltas.
- **`theme`** has a single value and cycling it does nothing.
- **Version drift**: git tags reach `v0.8.0` while the package declares `0.1.0`.
- Command completion covers command names only, not arguments. Main-screen feedback is a one-line message that the next keypress clears.

## Development

```bash
pip install -e ".[dev]"      # or: uv sync --extra dev
pytest --cov=vimtg           # tests, ResourceWarning is an error
ruff check src/ tests/
mypy src/                    # strict
```

Tests mirror the source tree under `tests/` with a `db_factory` fixture and autouse XDG isolation, so no test touches your real config or database. TUI screens are tested headlessly through the editor session.

| | |
|:--|:--|
| **Python** | 3.12+, strict mypy |
| **TUI** | Textual + Rich |
| **CLI** | Click |
| **HTTP** | httpx |
| **Search** | SQLite FTS5 |
| **Cards** | Scryfall bulk data (offline) |
| **Theme** | Catppuccin Mocha |
| **Build** | Hatchling |
| **Tests** | pytest, pytest-cov, pytest-asyncio |
| **Lint** | Ruff |

## License

MIT

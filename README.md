```
         _           _
  __   _(_)_ __ ___ | |_ __ _
  \ \ / / | '_ ` _ \| __/ _` |
   \ V /| | | | | | | || (_| |
    \_/ |_|_| |_| |_|\__\__, |
                         |___/
```

**Vim-powered Magic: The Gathering deck builder for the terminal.**

`j`/`k` to navigate · `dd` to delete · `o` to add a card · `:wq` to save · plain text decks that live in git

---

Your decks are plain text files. Your editor speaks vim. Your card database is local: 30,000+ Scryfall cards searchable in milliseconds, no internet required after the first sync. Mana costs render in color, card details expand inline under the cursor, legality problems show up as gutter signs while you type, and a snapshot history lives alongside every deck.

Built with [Textual](https://textual.textualize.io). Styled in [Catppuccin Mocha](https://github.com/catppuccin/catppuccin). Designed for people who think in keystrokes.

<!-- Absolute URL so the demo also renders on PyPI. Regenerate with
     `uv run vhs docs/demo.tape` (see the header of docs/demo.tape). -->
![vimtg in a terminal: opening a 100-card Krenko, Mob Boss Commander deck, expanding card details inline, searching the card database for Goblins that make tokens, jumping to a card with /, opening the analytics pane with the mana curve, and drawing a seeded sample hand](https://raw.githubusercontent.com/k8rthik/vimtg/main/docs/demo.gif)

*A Commander deck in 30 seconds: inline card details, card search, mana curve, and a sample hand (`:hand`).*

## Install

vimtg is a terminal app for Python 3.12+ on Linux, macOS, and Windows. Install it as an isolated tool:

```bash
pipx install vimtg          # or:
uv tool install vimtg
```

> **Note:** the first PyPI release is upcoming. Until it is published, install from git:
>
> ```bash
> pipx install git+https://github.com/k8rthik/vimtg.git
> # or
> uv tool install git+https://github.com/k8rthik/vimtg.git
> ```

Check it worked with `vimtg --version`. Upgrade later with `pipx upgrade vimtg` or `uv tool upgrade vimtg`.

## Quick start

A 60-second tour, from an empty directory to a saved deck:

```bash
vimtg tutor                     # optional: a 15-minute hands-on lesson deck, works offline
vimtg sync                      # one-time: download Scryfall card data (~25 MB) and oracle tags (~6 MB)
vimtg new "Burn" -f modern      # scaffold Burn.deck in the current directory
vimtg Burn.deck                 # open it in the editor
```

Inside the editor:

1. Press `o` to open a card search below the cursor, type `lightning bolt`, and press `Enter` (`Tab` cycles through matches). Prefix a count for copies: `4o`.
2. Move with `j`/`k`, `gg`/`G`; bump a quantity with `+`/`-`; delete a line with `dd`; undo with `u`.
3. `:w` saves (and snapshots the deck in its history), `:q` quits, `:q!` quits without saving, `:wq` does both.
4. Press `F1` (or type `:help`) any time for help; it opens on a "Getting started" section. `g?` toggles a short cheat sheet of the most used keys.

A deck with no cards and a blank name or format (greeter `n`, `vimtg new "Burn"` without `-f`, or `vimtg name.deck` for a file that does not exist yet) first asks for its name and format: `Tab` completes the format, `Esc` skips. A new deck's first `:w` writes `<deck-name>.deck` in the current directory.

vimtg is modal like vim: `Esc` always returns to normal mode. A stray `q` starts recording a macro (the status line says `recording @a (q stops)`); press `q` again to stop. Missed a message? `:messages` shows the recent ones.

Back in the shell, `vimtg info Burn.deck` summarises the deck and `vimtg validate Burn.deck` checks legality for its `// Format:`. Running `vimtg` with no arguments opens a greeter with recent decks, import, and sync.

No API keys are needed for anything.

## Network and privacy

vimtg works offline once card data is downloaded. It makes **no telemetry, analytics, or crash-reporting requests**, has no accounts, and needs no credentials. The only network requests are:

| When | Where | What |
|---|---|---|
| `vimtg sync`, the greeter's `[s]`, or the TUI's background auto-sync (on launch and hourly, only when card data is missing or more than seven days old) | `api.scryfall.com`, `data.scryfall.io` | The public `oracle_cards` bulk file (card text, legalities, prices; ~25 MB) and the `oracle_tags` bulk file (Scryfall's `otag:` tags; ~6 MB). Turn auto-sync off with `:set noautosync` or `VIMTG_NO_AUTOSYNC=1`. |
| You open the EDHREC pane (`Space r` / `:edhrec`) on a Commander deck | `json.edhrec.com` | Recommendations for your commander's name. Cached for seven days (offline, an older cached page is shown and says how old it is); disable with `VIMTG_NO_EDHREC=1`. |
| You import a deck URL (`:import <url>` or the greeter's `[i]`) | The site in the URL: Moxfield, Archidekt, ManaBox, Deckstats, TappedOut, or MTGGoldfish | That one public deck. |

Requests identify themselves with a `vimtg/<version>` User-Agent and send nothing about your decks except the commander name (EDHREC) or the deck URL you asked to import. Your decks, settings, and history stay on your machine: card data and history in `~/.local/share/vimtg/`, config in `~/.config/vimtg/`, download caches in `~/.cache/vimtg/` (XDG variables are honoured).

## Documentation

- [Deck file format](https://github.com/k8rthik/vimtg/blob/main/docs/deck-format.md)
- [Keybindings](https://github.com/k8rthik/vimtg/blob/main/docs/keybindings.md)
- [Ex commands](https://github.com/k8rthik/vimtg/blob/main/docs/commands.md)
- [Changelog](https://github.com/k8rthik/vimtg/blob/main/CHANGELOG.md)

The rest of this page is a full feature tour.

## Contents

- [The `.deck` format](#the-deck-format)
- [Feature rundown](#feature-rundown)
  - [Vim editing engine](#vim-editing-engine)
  - [Card database and search](#card-database-and-search)
  - [Adding cards](#adding-cards)
  - [Zones](#zones)
  - [Sections, layouts, and placement](#sections-layouts-and-placement)
  - [Categories](#categories)
  - [Bulk editing](#bulk-editing)
  - [Format-aware validation and live lint](#format-aware-validation-and-live-lint)
  - [Sideboard plans](#sideboard-plans)
  - [Analytics](#analytics)
  - [Collection](#collection)
  - [Sample hand](#sample-hand)
  - [The side pane and EDHREC](#the-side-pane-and-edhrec)
  - [Import, export, and clipboard](#import-export-and-clipboard)
  - [Version control](#version-control)
  - [Greeter](#greeter)
  - [Configuration](#configuration)
  - [Help](#help)
- [Keybindings](#keybindings)
- [Commands](#commands)
- [CLI](#cli)
- [Known gaps](#known-gaps)
- [Contributing](#contributing)
- [License and attribution](#license-and-attribution)

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
| Card entry | `N Name  @category  #tag #tag  // comment` | The quantity is required: a bare `Lightning Bolt` or `4x Shock` line is not a card, and the editor, `vimtg validate` and `vimtg info` warn about it. Two-space delimiters keep double-faced names like `Fire // Ice` unambiguous. |
| Plan header | `VS: Matchup  // note` | Starts a sideboard plan block. |
| Plan entry | `-N Card` / `+N Card` | Indented under `VS:`. Never counted as deck cards. |
| Comment | any other `// text` | Freeform, preserved. |

Zones: `DCK` mainboard (implicit when no prefix or block applies), `SB` sideboard, `MB` maybeboard (a scratchpad never counted toward size or copy limits), `CMD` command zone (up to two partners, quantity 1), `CMP` companion (one, quantity 1, must actually have the Companion ability).

Header counts such as `// Creatures (12)`, `DCK: (60)`, `// Deck: Burn · 60/15 cards`, and `VS: Tron (-4 +4)` are rendered in the editor and never written to disk.

Full spec: [docs/deck-format.md](https://github.com/k8rthik/vimtg/blob/main/docs/deck-format.md).

## Feature rundown

### Vim editing engine

The editor engine has no dependency on Textual. Keys flow through a translator, a macro recorder, a remapper, a key-sequence parser, and then a session handler, so everything below is testable headlessly.

- **Modes**: Normal, Insert, Visual, Visual-line, Command, Search. Insert has four submodes: card search (`o`/`O`/`c`), line edit (`i`), the category and filter prompts (`gc`, `Space f`), and comment input (`A`). `Escape` always returns to Normal.
- **Motions**: `j`/`k` (skip blank lines), `w`/`b` (next/previous card), `{`/`}` (previous/next section), `[[`/`]]` (previous/next section or plan header), `gg`/`G`, `{count}G` or `{count}gg` (go to line), `Ctrl-D`/`Ctrl-U` (half page), `H`/`M`/`L` (top/middle/bottom of the visible deck view, inside the scroll-off margin so the view stays put; `3H`/`3L` count in from the edge), `/`/`?` (regex search forward/backward), `n`/`N` (repeat the last search in the same/opposite direction), `*`/`#` (search for the card under the cursor). `zz`/`zt`/`zb` scroll the view around the cursor. Any motion takes a count. The deck is line-oriented, so there is no column cursor and no `h`/`l`/`0`/`$`. `H`/`M`/`L` are not operator targets.
- **Operators**: `d`, `y`, `c` compose with motions and double up as `dd`, `yy`, `cc`. Counts multiply (`2d3j` is six lines). `j`/`k`/`G`/`gg` are linewise (`dj`/`dk` use raw line arithmetic; `d8G` stops at line 8, `dG` runs to the end); `w`/`b`/`{`/`}`/`[[`/`]]` are exclusive as in vim, so `dw` deletes one card and `d}` stops at the end of the section. `c` deletes and opens card search. `x` deletes the card under the cursor. `p`/`P` put below/above; `3p` puts three copies.
- **Quantity**: `+`/`-` adjust the count (`10+`, `3-`). `-` at zero deletes the line. Both preserve zone prefixes, plan signs, `@category`, `#tags`, and comments.
- **Line editing**: `i` edits the current line in place. On a `// Key:` metadata line the prefix is locked and only the value is editable. On `// Format:` the value ghost-completes from the known formats and warns when you confirm an unknown one. `A` adds or edits the card's inline comment.
- **Visual mode**: `v`/`V` select, `d`/`y`/`c`/`x` act on the range, `+`/`-` and the `z` zone and plan keys act on every card in it (one undo step), `o` swaps the selection ends. The category prompt honours the visual range.
- **Registers**: `"a`–`"z` named, `"A`–`"Z` append, unnamed, yank register `0`, delete history shifted through `1`–`9`, black hole `"_`, and the clipboard register `"+`/`"*` (yanks and deletes also copy to the system clipboard via OSC52).
- **Marks**: `m{a-z}` set, `'{a-z}` jump, all 26 letters. Marks shift correctly through inserts, deletes, puts, and zone moves. `Ctrl-O` / `Ctrl-I` walk vim's jumplist and `''` returns to before the latest jump.
- **Macros**: `q{a-z}` record, `q` stop, `@{a-z}` play, `@@` replay last, `3@a` plays three times, `@:` repeats the last ex command. Playback re-feeds keys through the full pipeline.
- **Dot repeat**: `.` replays the last change: operators (`c` together with the card it added), `o`/`O` with their card and copies, puts, quantity, `x`, zone and plan moves, categories, comments, `i` line edits, and `:s`. A visual change repeats on as many lines; a count on `.` overrides the recorded one.
- **Command line**: `Up`/`Down` recall history (prefix-matched, separate for `:` and searches, kept across sessions in `~/.local/state/vimtg/`), `Ctrl-W`/`Ctrl-U` delete a word / to the start, `Ctrl-B`/`Ctrl-E` and `Left`/`Right` move, `Backspace` on an empty line leaves the prompt. The card-search prompt has the same line editing.
- **Undo/redo**: `u`/`Ctrl-R`, counted. Session history is a linear undo stack: `u` walks back, `Ctrl-R` walks forward, and a new edit after an undo discards the redo entries. Each change is its own undo step, as in vim; only a quick burst of `+` or `-` on a card (within two seconds, not interrupted by an undo) collapses into one step. Undoing back to the loaded or last-saved state clears the modified flag.
- **Remapping**: `:map key action` (session-only, multi-character targets allowed, `:`-prefixed targets auto-submit), `:unmap key`, bare `:map` lists. Persistent maps live in `[keybindings]` in `config.toml`, per mode.
- **Which-key**: when a key sequence is pending (`d`, `y`, `c`, `g`, `[`, `]`, `"`, `q`, `@`, `m`, `'`, `Ctrl-W`, `Space`, `t`, `z`) a popup titled by the prefix shows the possible completions, derived from the same key spec as the help overview. The status line shows the pending sequence and counts.
- **Mouse**: wheel and trackpad scroll the deck view and the side pane (EDHREC or analytics), vim-style: three lines per notch, the cursor is dragged only when it would leave the scroll-off band. There is no click-to-position.

### Card database and search

- **Offline Scryfall data**: `vimtg sync` downloads the `oracle_cards` bulk file, streams it into SQLite, and builds an FTS5 index over name, type line, and oracle text. Tokens, emblems, and art-series cards are skipped. Downloads are content-length checked and written atomically; a corrupt cache is deleted and reported. Each sync replaces the card table in one transaction, so a card Scryfall re-keys or drops never lingers as a stale duplicate; deck history is never touched.
- **Oracle tags**: after the cards, the same sync downloads Scryfall's `oracle_tags` file (about 4,600 tags such as `ramp`, `removal`, `tutor`, `card-advantage`, with their hierarchy and aliases) and stores every card's tags with their ancestors, so `otag:removal` finds `removal-burn` cards as it does on Scryfall. If the tags download fails the cards still load and the sync says the tags were skipped; an `otag:` search on a database without tags says `oracle tags not synced`.
- **Card names**: cards resolve by full name or any face, so `Fable of the Mirror-Breaker`, `Stomp`, `Fire/Ice`, `lightning bolt`, and `Lim-Dul's Vault` all find their card in lint, validation, stats, export, and the inline card details.
- **Auto-sync**: the TUI checks on launch and hourly, and syncs on a worker thread when the database is missing or older than seven days. A toast reports success or failure, and search and lint light up retroactively once data arrives. Disable with `:set noautosync` or the `VIMTG_NO_AUTOSYNC` environment variable.
- **`:sync`** (`:sync!` to re-download) runs the same background sync on demand; editing continues and the status line shows its progress. The status line always says what card data you have: `card data as of <date>` (highlighted once older than seven days), or `no card data - :sync to download` while there is none. Offline, card search says so instead of showing an empty list, and `vimtg validate` adds an informational note when the data is more than a week old. Sync errors explain themselves: offline, a proxy refusing or wanting credentials, TLS interception.
- **Damaged database**: on launch (and on `vimtg sync`) the database gets an integrity check. A damaged file never blocks the editor: it is copied byte for byte to `cards.db.corrupt-<timestamp>`, a fresh database is built with every deck snapshot that can still be read, and a warning says how much history came back and where the backup is. Card data is then re-downloaded with `:sync`.
- **Query syntax**: Scryfall-style, shared by the overlay and `vimtg search`. Bare words prefix-match card names (any face); `!"Exact Name"`; `t:`, `o:` (with `/regex/`), `kw:`, `m:`; `c:`/`id:` with colour letters or names (`c:boros`, `id<=esper`) and `= != < <= > >=`; `mv`, `pow`, `tou`, `usd`/`eur`/`tix` comparisons; `r:`, `set:`, `f:`/`banned:`/`restricted:`; `is:commander`, `is:dfc`/`mdfc`/`split`/`adventure`; `otag:` (Scryfall oracle tags: `otag:ramp`, `otag:removal`, `otag:tutor`); `-` negation, `or`, and parentheses. Unknown keys and bad values are reported by name. Full reference: [docs/search.md](https://github.com/k8rthik/vimtg/blob/main/docs/search.md).
- **Format filtering**: in the editor, search results are filtered to cards legal or restricted in the deck's declared format when that format is known, before `search_limit` is applied. When the filter leaves nothing, the overlay says so: `No matches legal in modern (3 more in other formats)`, and `Enter` there closes the search with that message.
- **Card model**: name, mana cost, CMC, type line, oracle text, colours, colour identity, P/T, set, rarity, five price sources (USD, USD foil, EUR, EUR foil, tix), legalities, layout, keywords. Transform and modal DFCs use the front face (search also reads the back face's rules text); split and adventure cards join both faces.

### Adding cards

- `o`/`O` open a search prompt below/above the cursor. A count sets copies: `4o` adds four of the confirmed card.
- Results update from two characters on a worker thread, up to `search_limit`. The overlay shows up to ten rows with name, colourised mana cost, type line, and price, plus a one-line oracle preview for the selected row. The top match becomes a ghost in the command line.
- `Tab`/`Ctrl-J`/`Ctrl-N`/`Down` next, `Shift-Tab`/`Ctrl-K`/`Ctrl-P`/`Up` previous, `Enter` confirms, `Escape` discards the scratch line and restores the cursor.
- Confirming a card already in the same zone bumps its quantity instead of adding a line.
- The new card follows the cursor's zone. Inside a `SB:`/`CMD:` block it lands there in matching style. In the mainboard it is filed by the placement policy (see below). Inside a `VS:` block the search runs against the deck's own cards and writes a signed plan line.
- **Inline expansion**: with `auto_expand` on, the cursor's card renders a detail block under it: type line and P/T, word-wrapped oracle text, set, rarity, and price. `K` shows it for the cursor card when `auto_expand` is off, and hides it when on. The deck view windows by rendered rows so the expansion never clips.

### Zones

`zs` / `zm` / `zd` / `zc` / `zp` move the cursor card to the **s**ideboard, **m**aybeboard, main **d**eck, **c**ommander zone, or com**p**anion slot. The bare key moves all copies; `2zs` splits two off. Moving into a zone that already holds the card merges quantities and unions tags; `zc` of a card that cannot be the commander moves it and says why. Category, tags, and comments travel with the card. A move that creates a brand-new zone opens it as an indented block; moves into existing zones match the style already in use.

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
- **Filters**: `Space f` or `:filter expr` dims every card whose category fails the expression and suppresses its expansion. `ramp|draw` is OR, `-removal` is NOT, `ramp -removal` is AND NOT; `Tab` completes the deck's categories, most used first. `:filter!` or an empty expression clears.
- A card line may also carry `#tag` tokens written by other tools or by earlier vimtg versions. vimtg reads and writes them unchanged (sorted on write) but no longer edits them. `:dtag` / `:duntag` edit the deck-level `// Tags:` line.

### Bulk editing

Most commands take a vim range: `%`, `5,10`, `.`, `$`, or a mark pair (`'a,'b`).

- `:sort [field]` sorts the current section (or range) by `name`, `qty`, `cmc`, `type`, `color`, `category`, `power`, `toughness`, `rarity`, or `price`. Entries are sorted within each zone so a range spanning zones never rezones a line. `:sort!` reverses. Missing card data falls back to name order.
- `:s/pat/rep/[gI]` substitutes a regex across the range (`:%s/Bolt/Helix/g`), case-insensitive unless `I`.
- `:g/pattern/cmd` and `:v/pattern/cmd` run `cmd` on matching or non-matching card lines in every zone: mainboard, sideboard, maybeboard, command zone, and companion, block or prefix style. `cmd` is `d` (delete), `p` (list the matches), `y [x]` (yank into register `x`), or `s/pat/rep/` (substitute). The pattern sees the whole line, so `:g/^SB:/d` or `:v/@ramp/d` work. Headers, comments, metadata, and sideboard-plan entries never match.
- `/pattern` jumps to the next matching card, case-insensitive regex, wrapping (`?` searches backward). `n`/`N` repeat it forward/backward.

### Format-aware validation and live lint

Formats with rules (names are Scryfall legality keys): standard, pioneer, modern, legacy, vintage, pauper, historic, timeless, explorer, alchemy, gladiator (100-card singleton, no sideboard), premodern, penny (Penny Dreadful), commander, brawl (100-card Brawl), standardbrawl (60-card), oathbreaker, paupercommander, duel (Duel Commander). Names are case-insensitive and accept the aliases card search accepts (`EDH`, `PDH`, `Historic Brawl`, `Standard Brawl`, `Duel Commander`; see [docs/search.md](https://github.com/k8rthik/vimtg/blob/main/docs/search.md)). Any other `// Format:` value gets a warning listing these. Legality comes entirely from the synced Scryfall data; there are no hard-coded ban lists.

- **Live gutter signs**: `✗` error and `!` warning in a two-character column. The reason appears in the status line when the cursor is on the line. The status line also totals `✗N` and `!N`.
- **Checks**: invalid quantity, unknown card, unknown format, banned/not-legal/restricted cards (warnings only in the maybeboard), copy limits across main + side + command zone with basic lands exempt and oracle text honoured ("any number of cards named" Relentless Rats, "up to seven" Seven Dwarves), minimum or exact deck size, sideboard allowed and size (over the limit is an error; a companion counts toward the 15 unless it is already listed in `SB:`), companion count, quantity, actual Companion ability, and colour identity in commander formats, commander present, quantity 1, at most two, eligible (legendary creature or Vehicle, "can be your commander", or a Background beside a "Choose a Background" commander; Brawl also allows planeswalkers, Pauper Commander any creature, Oathbreaker a planeswalker plus its Signature Spell, and a missing Signature Spell is an error), partner-pair heuristic, and colour identity of every mainboard card.
- **Plan lint**: an out must be in the mainboard, an in must be in the sideboard, never more copies than the zone holds, a missing sign is an error; unbalanced ins/outs, duplicate plan names, and a card listed twice are warnings.
- `:validate` prints the full list; `vimtg validate deck.deck` prints the same report from the shell and exits non-zero on errors. Without a card database both say legality checks were skipped and suggest `:sync` (`vimtg sync`). `vimtg validate --strict` also fails on warnings such as unknown card names, and needs a synced card database. For Commander decks both also show the Game Changer count and an estimated bracket (an `info:` line in the shell). This line never fails validation, even with `--strict`.

### Sideboard plans

A plan is a `VS: <matchup>` block of `-N Card` (out of the mainboard) and `+N Card` (in from the sideboard) lines, kept at the end of the file.

- `:plan <matchup>` activates a plan, creating its block when new. Bare `:plan` cycles, `:plan!` deactivates, `:plans` lists every plan with `-out +in` totals. `]v`/`[v` jump between plans and activate them. A deck with exactly one plan auto-activates it.
- `zo`/`zi` board the cursor card out/in of the active plan (all copies, or `2zo` for two), clamped to what the zone holds; entries are removed at zero.
- The deck view shows each card's `-N`/`+N` delta for the active plan, plan headers show `(-4 +4)` with `!` when unbalanced, and the status line shows `vs Tron -4/+4`.
- Inside a plan block, `o` searches the deck's own cards, `+`/`-` adjust counts, and `dd` removes an entry.
- `:export guide` and `vimtg guide --markdown` write the plans as a Markdown sideboard guide.

### Analytics

- `:analytics` (or `Space a`) opens a live pane that recomputes on every edit: **curve** bar chart (0 to 7+), **types**, **zones**, **categories** (when used), **mana base** with per-colour pips, sources versus needed (Karsten-style requirement scaled to deck size), a `✓`/`✗ need N more` verdict and a suggested land count, **commander bracket** (Commander decks: Game Changers and an estimated bracket), and **draws**: exact hypergeometric odds of two lands in the opener, three land drops by turn 3, and a cursor-following line giving the opener and by-turn-3 odds for the card under the cursor. With a plan active the whole pane shows the post-board deck.
- The commander counts toward totals, curve and pips. Modal double-faced spells with a land back count as spells, not lands. Sources come from the mana a land produces plus the lands it can fetch; hybrid and Phyrexian symbols count as pips. [docs/analytics.md](https://github.com/k8rthik/vimtg/blob/main/docs/analytics.md) has the details, and explains why the bracket estimate is only a heuristic.
- `vimtg info deck.deck` prints the deck's name, its format (the `default_format` setting when the deck names none), the card count of every zone in use (commander, companion, mainboard, sideboard, maybeboard) and, with card data, a one-line summary: card count, average CMC, cards per type, and total price labelled with its price source (`$123.45 (usd)`; the `price_source` setting switches it).

### Collection

- `:collection path.csv` loads your collection from a ManaBox, Moxfield, Archidekt, or Deckbox export, or any CSV with a name column and a count column (headers matched case-insensitively). Copies are summed across printings; vimtg does not track printings. The path is saved to the `collection` setting and reloaded on every deck open when the file changed; a missing or unreadable file shows one warning and leaves the deck usable. Bare `:collection` reports `Collection: N cards (M unique) from file`; `:collection!` forgets it.
- With a collection loaded, a card line you cannot cover gets a dim `○` in the gutter (a lint `✗` or `!` wins the one cell), the inline card detail ends with `owned 2 of 4` or `not owned`, and the analytics pane gains a **collection** block: `Owned 54/60`, `Missing 6 (4 unique)`, `To complete $12.30` in your `price_source` (plus `, 2 unpriced` when some missing cards have no price). Mainboard and sideboard both count; the same card in both shares one owned pool, allotted to the mainboard first.
- `:export missing [file]` writes the missing cards as `N Card Name` lines, mainboard then a blank line then sideboard, which pastes into any store's mass-entry box; with no file it goes to the clipboard. `vimtg missing deck.deck [--collection file.csv]` prints the same list on stdout and the total cost on stderr.

### Sample hand

- `:hand` (alias `:goldfish`, key `Space h`) opens a goldfish overlay: it shuffles the main deck and draws an opening seven. Sideboard, maybeboard, commander and companion cards stay out of the library; for Commander the commander is shown in the command zone and the hand comes from the 99. With a sideboard plan active, the post-board deck is used.
- `n`/`Space` draws the next card, `m` takes a London mulligan (draw seven, then select cards with `j`/`k` and press `b` to put one on the bottom per mulligan; the first mulligan is free in Commander and Brawl), `r` reshuffles a fresh hand, `gg`/`G` and `Ctrl-D`/`Ctrl-U` move the selection as in every list, `?` opens the hand help topic, `q`/`Esc` closes.
- The overlay shows the land count in hand and hypergeometric odds: at least one / two lands in the opening seven, and the chance of hitting every land drop through turns 1 to 5, on the play and on the draw. Lands come from the card database; without one, only basic lands are counted.
- `:hand seed=42` seeds the shuffle so the same hands come up every time (useful for tests and comparisons).
- `vimtg hand deck.deck [--seed N] [--draws N] [--plan NAME]` prints a sample hand, any extra draws and the odds from the shell.

### The side pane and EDHREC

One pane at a time, beside the editor when the terminal is at least 60 columns wide (narrower terminals hide it until there is room again).
- **EDHREC pane** (`Space r`, `:edhrec [type]`): recommendations for the commander(s) on the deck's `CMD:` lines, Commander-only, partner pairs supported. Tabs: Top, Creatures, Instants, Sorceries, Artifacts, Enchantments, Planeswalkers, Battles, Lands. Each row shows inclusion rate and synergy score; `✓` marks cards already in the deck. `h`/`l` switch tabs, `Enter` adds the selected card to its type section. Responses are cached for seven days in the XDG cache directory; offline, an older cached page still opens, its header saying `cached N days ago (offline)`. `VIMTG_NO_EDHREC` disables lookups.
- **Analytics pane** (`Space a`, `:analytics`): described above; opens unfocused because it is a readout. `Space a` / `Space r` again close their pane.
- `Ctrl-W w` switches focus between the editor and the pane; `:close`, or the pane's own `Space` key again, closes it. A focused pane has an orange border; in it `q` closes the pane and `Esc` returns to the editor. Any editing key (and `gh`, `g?`, `gc`) falls through to the editor and refocuses it.

### Import, export, and clipboard

- **Formats**: vimtg, MTGO text, MTGO `.dek` XML, Arena, Moxfield CSV, Archidekt CSV, and a Markdown sideboard guide (export only). `:import file` auto-detects the format and opens the deck as a new unnamed buffer, as the greeter's import does, so the next `:w` never overwrites the deck that was open (unsaved changes refuse with E37, `:import!` discards them); `:export fmt [file]` writes it (no file: copies it to the clipboard). `vimtg convert` does the same from the shell. Every import (`:import`, the greeter, `vimtg convert`) runs the same steps: names resolve to each card's official name against the synced card database when there is one, the deck is grouped by card type, duplicates merge, and skipped lines and unknown cards are reported.
- **No accidental overwrites**: `:export fmt file` refuses an existing file (E13) unless you write `:export!`, and never writes over the deck you have open; `vimtg convert -o` refuses an existing file without `--force` and never overwrites its input. Writes are atomic. `vimtg convert deck.deck --to vimtg` copies the deck file unchanged.
- **Imports are laid out like a new deck**: `// Deck:` and `// Format:` lines (the message reminds you when the format is unknown), then `CMD:` / `DCK:` / `SB:` blocks, with type sections when card data is synced. Imported names become each card's official name (`Fire/Ice` → `Fire // Ice`, `Insectile Aberration` → `Delver of Secrets // Insectile Aberration`), so copies merge and count per card.
- **URL import** from Moxfield, Archidekt, ManaBox, Deckstats, TappedOut, and MTGGoldfish via `:import <url>` or the greeter's `[i]` prompt. Commanders, companions, Oathbreaker signature spells, sideboards, and maybeboards map to the right zones; the deck title lands in `// Deck:`, the site's format in `// Format:` (Moxfield, Archidekt), and the URL in `// Source:`. No API keys needed.
- **Clipboard**: `:clipboard [fmt]` copies the deck (Arena by default) with `pbcopy`, `wl-copy`, `xclip`, `xsel`, or `clip.exe` when one works, else through Textual's OSC 52 support (iTerm2, kitty, Alacritty, WezTerm, Windows Terminal; tried first over SSH). The message says which happened: OSC 52 cannot be confirmed, and when nothing works you are told so instead of "Copied".
- **Paste**: your terminal's paste works everywhere. In card search and on the `:` line the text is inserted at the cursor; in normal mode a pasted decklist (any import format) is **added** to the deck as one undo step, each card into its own zone, with skipped lines reported. `:import` with no argument opens the clipboard's decklist (or fetches the deck URL on it) as a new unnamed deck in place of the open one. The greeter opens a pasted decklist directly.
- **Text imports** (MTGO `.txt`, Arena, Moxfield/Archidekt text exports, pasted lists) share one parser: `4 Card` and `4x Card` lines, and bare `Card` lines as one copy; trailing `@category` / `#tag` tokens; `Deck`/`Commander`/`Companion`/`Sideboard`/`Maybeboard` headers; `SB:` prefixes; and MTGO's headerless blank-line sideboard divider (only when the list is exactly two blank-separated groups). In that two-group shape, a group of one or two single cards beside a ~100-card list (Moxfield's Commander export, commander first or last) is the command zone, not a sideboard; with card data a legendary leader of a 60-card Brawl/Oathbreaker list is recognised too. Printing suffixes such as `(ZEN) 126 *F*`, `(PLST) ELD-115`, and `(CMM) 400a` are stripped. Archidekt's `Categories` column and `[Category]` suffixes place commander, sideboard, and maybeboard cards. A UTF-8 BOM and CRLF line endings are fine, and duplicates of one card (`Lightning Bolt` + `lightning bolt`, `Fire // Ice` + `Fire/Ice`) are merged.
- Lines an import cannot read are reported, not dropped: `:import` shows the count and the first one, and `vimtg convert` lists each on stderr.
- Hand-edited `.deck` files may use a bare `Sideboard` line instead of `SB:` prefixes; card lines after it are sideboard cards.
- Export quirks worth knowing: MTGO text and `.dek` park commander and companion cards in the sideboard so they are not lost; MTGO, `.dek`, and Arena exports write each card's official client name — the front face for double-faced and adventure cards (`4 Stomp` exports as `Bonecrusher Giant`), both halves for split cards (`Fire // Ice`) — and Arena lines carry no set code; Moxfield and Archidekt CSV exports write the full official name; Archidekt export writes a `Categories` column (Commander, Companion, Sideboard, Maybeboard, or the card's `@category`) so zones survive.

### Version control

Two layers, both stored in the local SQLite database and keyed by deck path.

- **Session undo stack**: `u`/`Ctrl-R` as described above.
- **Persistent history**: every deck has one linear chain of snapshots in the database. `:commit "msg"` snapshots the deck (deduplicated by content hash), `:checkpoint name` commits and tags, and `:w` auto-snapshots when `auto_snapshot` is on. The status line shows how many snapshots the deck has.
- **History overlay** (`gh`, `:history`, `:log`): a floating lazygit-style window over the editor, lazy.nvim style, with the editor dimmed behind it. Panels: Working copy (uncommitted changes against the latest snapshot, `c` commits), Snapshots (7-char id, timestamp, tag, description), Diff (added, removed, quantity changed, section moved, grouped by zone), and Stats delta (card count, average CMC, price in your configured currency, per-bucket curve delta). Keys: `1`–`4` or `Tab` to pick a panel, `j`/`k`, `gg`/`G`, `Ctrl-D`/`Ctrl-U` or the wheel to move or scroll, `Enter` to open the item in the Diff panel, `c` commit, `t`/`T` tag/untag, `R` restore, `d` toggle unchanged cards, `q`/`Escape`/`gh` close. Restore loads the snapshot into the editor in place, keeping the cursor row, as a new snapshot on top of the history.

### Greeter

`vimtg` with no arguments opens a greeter with the logo, version, and recent decks: the ones you opened or saved lately from any directory (remembered in `~/.local/state/vimtg/state.json`), then the newest `.deck` files in the current directory. On short terminals the logo and recents give way so the menu always fits. Keys: `n` new deck (asks for its name and format), `e` file browser, `i` import from a file path or deck URL (bracketed paste supported), `s` sync cards with inline progress (hidden while a sync runs), `r` recent files, `1`–`5` open a recent deck, `R` unsaved buffers left by an earlier session (shown only when there are any; `Enter` opens one, `d` discards it), `t` the tutor, `?` help, `q` quit, and `:` for a small command line running the editor's `:e {file}`, `:enew`, `:q`, `:sync`, `:help [topic]` and `:Tutor` (`Tab` completes). `:home` returns here from the editor.

### Configuration

Settings live in `~/.config/vimtg/config.toml` under `[editor]`; malformed values fall back to defaults per field and never block startup. A file that is not valid TOML loads as defaults with a warning, and `:config` refuses to save over it (it backs it up to `config.toml.bak` instead) until it is fixed. Change them with `:set key=value` (`:set number`, `:set nonumber`, bare `:set` lists all) or in the `:config` screen (`j`/`k`, `h`/`l` cycle, `s` save, `q` close). Both save to `config.toml` right away, so a change lasts across sessions (unlike vim's `:set`). Saving edits the file in place: comments, other tables such as `[keybindings]`, and key order are kept; only a file laid out in a way the editor cannot update line by line (dotted `editor.key` names, an inline `editor = {…}` table) is rewritten without its comments. A wrong-typed value or a wrong-shaped `[keybindings]` entry is skipped with a warning naming it (also kept in `:messages`).

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
| `default_format` | blank or any format listed under [validation](#format-aware-validation-and-live-lint) | blank | Format used when the deck declares none |
| `confirm_quit` | bool (`confirmquit`) | on | Require `:q!` when modified |
| `auto_snapshot` | bool | on | Commit to the VCS on `:w` |
| `auto_sync_cards` | bool (`autosync`) | on | Background card download when missing or stale |
| `collection` | path | blank | Your collection CSV (ManaBox, Moxfield, Archidekt, Deckbox, or any name+count CSV), set with `:collection` and reloaded on deck open |

Where things live (XDG-aware): card database plus deck snapshots in `~/.local/share/vimtg/cards.db`; config and the category history in `~/.config/vimtg/`; Scryfall bulk files and the EDHREC cache in `~/.cache/vimtg/`. Deck files are ordinary files wherever you keep them; there is no managed deck directory.

### Help

Empty decks show a short "Getting started" tips panel under the deck, kept through the first cards until the first `:w` (`Esc` hides it, `:tips off` turns it off for good, `:tips` shows it again); `:help` opens on the same "GETTING STARTED" section. Listing commands (`:registers`, `:marks`, `:categories`, `:plans`, `:validate`, `:g/pat/p`) print on the command line when the output fits on one line, and otherwise open it in a floating pager, one entry per line (vim's more-prompt). Messages on the command line vanish at the next key, except errors, which stay up while you move the cursor; `:messages` lists the last 100, together with pop-up notices (card sync results, database recovery, config warnings).

Below 30×8 the editor shows a "terminal too small" notice instead of a garbled layout; overlays (search results, the `g?` panel) are capped at about half the screen, and the side pane steps aside while the terminal is too narrow for it.

Help, `:messages`, `:config`, `:hand`, and the history overlay all open as the same floating window over the editor (titled on its top border, its close keys on the bottom one); a window opened from another, such as `?` in the history overlay, floats above both. `F1` or `:help` opens the help window; `g?` toggles a short cheat sheet under the deck, the rows the which-key popup shows (`F1` from it opens the full help). On a topic, `F1` switches the help window to the overview. The greeter's `?` and `F1` open the same help window. In the editor `?` is vim's backward search, not help; `:help <command>` opens that command's topic, under its full name or an alias (`:help export`, `:help exp`). The command line shows cursor-sensitive hints on card lines, plan lines, and elsewhere, and `:` commands fuzzy-complete with `Tab`/`Shift-Tab`. After a space, arguments complete too: `:layout` modes, `:sort` fields, `:filter` categories from the deck (the term after `+`, `|`, or `-`), and `:category`/`:cat` names from the deck, history, and presets.

## Keybindings

Normal mode unless stated. Five rules hold everywhere: one navigation vocabulary (`j`/`k`, `gg`/`G`, `Home`/`End`, `Ctrl-D`/`Ctrl-U`, wheel), one dismissal vocabulary (`q`/`Esc`; `Ctrl-C` is `Esc` and never quits), one help vocabulary (`F1` everywhere; `?` on screens other than the editor, where it is backward search), one job per editor prefix (`g` go, `Ctrl-W` the pane, `Space` the leader, `z` zones and scrolling, `m` marks), and one key spec that which-key, the help overview, and the drift tests all read. Full reference: [docs/keybindings.md](https://github.com/k8rthik/vimtg/blob/main/docs/keybindings.md).

<details>
<summary><strong>Modes and navigation</strong></summary>

| Key | Action |
|-----|--------|
| `i` | Edit current line (value only on metadata lines; a card in a zone block keeps its indentation) |
| `o` / `O` | Add card below / above (`4o` adds four copies) |
| `A` | Add or edit the card's inline comment |
| `:` / `/` / `?` | Command line / search forward / backward |
| `v` / `V` | Visual / visual-line |
| `j` / `k` | Down / up, skipping blanks |
| `w` / `b` | Next / previous card |
| `{` / `}` | Previous / next section |
| `[[` / `]]` | Previous / next section or plan header |
| `[v` / `]v` | Previous / next sideboard plan (activates it) |
| `gg` / `G` / `{n}G` | First / last / nth line (also `:{n}`) |
| `Ctrl-D` / `Ctrl-U` | Half page down / up |
| `H` / `M` / `L` | Top / middle / bottom of the visible view |
| `n` / `N` | Repeat the last search same / opposite direction |
| `*` / `#` | Search forward / backward for the card under the cursor |
| `zz` / `zt` / `zb` | Scroll the cursor line to center / top / bottom |
| `m{a-z}` / `'{a-z}` | Set / jump to mark (all 26 letters) |
| `Ctrl-O` / `Ctrl-I` (`Tab`) / `''` | Back / forward through the jumplist / back to before the latest jump |

</details>

<details>
<summary><strong>Editing</strong></summary>

| Key | Action |
|-----|--------|
| `dd` / `yy` / `cc` | Delete / yank / change line |
| `D` / `Y` / `S` / `C` | Same as `dd` / `yy` / `cc` / `cc` (decks are linewise) |
| `d` `y` `c` + motion | Operators (`dw`, `d}`, `y5G`, ...) |
| `x` | Delete card at cursor |
| `p` / `P` | Paste below / above |
| `+` / `-`, `Ctrl-A` / `Ctrl-X` | Increment / decrement quantity |
| `zs` `zm` `zd` `zc` `zp` | Move to sideboard / maybeboard / main / commander / companion |
| `zo` / `zi` | Board out of / into the active plan |
| `"{x}` | Use register `x` for the next operator (`"_` black hole, `"+` clipboard) |
| `q{x}` / `@{x}` / `@@` | Record / play / replay macro |
| `@:` / `gv` | Repeat the last ex command / reselect the last visual selection |
| `.` | Repeat last change |
| `u` / `Ctrl-R` | Undo / redo |

</details>

<details>
<summary><strong>Categories, filters, the pane</strong></summary>

| Key | Action |
|-----|--------|
| `gc` / `gC` | Set / clear category (Tab completes) |
| `gl` | Toggle type / category layout |
| `gh` | Toggle the history overlay |
| `Ctrl-W w` | Switch focus between the editor and the pane |
| `Space r` / `Space a` | Toggle the EDHREC pane / analytics pane |
| `Space h` | Sample hand / goldfish overlay |
| `Space f` | Filter the view by category (empty clears) |
| `F1` / `g?` | Full help / cheat sheet |
| `ZZ` / `ZQ` | Save if there are changes, then quit (`:x`) / quit discarding changes (`:q!`) |

</details>

## Commands

Type `:` to enter command mode. Full reference: [docs/commands.md](https://github.com/k8rthik/vimtg/blob/main/docs/commands.md).

<details>
<summary><strong>Command reference</strong></summary>

| Command | Description |
|---------|-------------|
| `:w [file]`, `:w!`, `:q`, `:q!`, `:wq`, `:x`, `:e[!] [file]`, `:enew[!]`, `:{n}`, `:home`, `:recover` | File and navigation (`:enew` opens a new unnamed deck and its wizard; `:w file` writes a copy and keeps editing this deck, as in vim, and `:saveas file` switches to it; a deck with no file yet is named after its `// Deck:` line, or takes the `:w file` name; overwriting another file or outside changes needs `:w!`; `:e file` opens another deck and `:e!` reloads this one, dropping changes; `:q` with a pane open closes the pane; `:12` goes to line 12; `:recover` loads the crash-recovery copy) |
| `:reg`, `:marks` | Show registers / marks |
| `:sort [field]`, `:sort!` | Sort section or range |
| `:s/pat/rep/[gI]` | Substitute (regex like `/`, case-insensitive unless `I`; `&` and `\1` in the replacement) |
| `:g/pat/cmd`, `:v/pat/cmd`, `:g!` | Run `d`, `p`, `y [x]`, or `s/pat/rep/` on matching / non-matching cards in any zone |
| `:cat name`, `:cat!`, `:categories`, `:layout [type\|category]` | Categories and layout |
| `:filter expr`, `:filter!`, `:dtag`, `:duntag` | View filter and deck tags |
| `:plan [name]`, `:plan!`, `:plans` | Sideboard plans |
| `:export fmt [file]`, `:import [file\|url]`, `:clipboard [fmt]` | Formats: arena, mtgo, dek, moxfield, archidekt, vimtg, guide; bare `:import` reads the clipboard; `:export missing` copies the cards your collection lacks |
| `:collection [path]`, `:collection!` | Load, report, or forget your collection CSV |
| `:sync`, `:sync!` | Download card data in the background (`!` re-downloads) |
| `:analytics`, `:edhrec [type]`, `:close` | The side pane |
| `:validate`, `:hand [seed=N]` | Legality, sample hand |
| `:history` (or `gh`), `:commit msg`, `:checkpoint name` | Version control |
| `:set [key=value]`, `:config`, `:map`, `:unmap` | Configuration |
| `:help [command]` | Help |
| `:messages`, `:messages clear` | Recent messages and errors |
| `:tips`, `:tips off`, `:tips on` | Getting-started tips panel |

</details>

## CLI

```bash
vimtg                                  # greeter
vimtg burn.deck                        # open a deck (vim-style); a new path is created on :w
vimtg new "Deck Name" -f commander     # scaffold a new deck in the cwd (-f shell-completes formats; --force overwrites)
vimtg sync [--force]                   # download or refresh the card database
vimtg tutor                            # the lesson deck, in an offline sandbox
vimtg search "t:creature mv<=2" -n 40  # search cards (docs/search.md); prices follow price_source/show_prices
vimtg search otag:ramp c:g             # Scryfall oracle tags work offline too
vimtg validate deck.deck [--strict]    # legality report; exit 1 on errors (--strict: warnings too)
vimtg info deck.deck                   # zones, format, and a stats line
vimtg missing deck.deck [--collection cards.csv]  # cards your collection lacks, store-pastable; total cost on stderr
vimtg guide deck.deck [--markdown]     # sideboard plans
vimtg hand deck.deck [--seed N] [--draws N] [--plan NAME]  # sample opening hand + land odds
vimtg convert in.dek --to arena -o out.txt   # --force overwrites an existing out.txt
vimtg convert https://moxfield.com/decks/ID --to dek   # a deck URL works too; --to takes every :export format
```

Notes, warnings and errors go to stderr; a command's own output (the deck, the validation report, search rows) goes to stdout, so it pipes cleanly.

## Known gaps

Known limitations; none block normal use.

- **No text objects and no till-motion** (`t` is unbound): the cursor moves by card line, not by character.
- **`:g`/`:v` run `d`, `p`, `y`, and `s///` only.** `:normal`, `:j[oin]`, `:>`/`:<`, `:r[ead]`, and `+N`/`-N` offsets are not supported ([details](https://github.com/k8rthik/vimtg/blob/main/docs/commands.md)).
- **History stats need the card database.** Without a synced database the Stats panel shows no deltas.
- **`:set` persists.** Unlike vim, it saves to `config.toml` at once; there is no session-only setting.
- Argument completion covers `:layout`, `:sort`, `:filter`, and `:category` only. `:validate` takes no argument (it reads `// Format:`, which already completes formats on `i`).

## Contributing

Bug reports, ideas, and pull requests are welcome. See [CONTRIBUTING.md](https://github.com/k8rthik/vimtg/blob/main/CONTRIBUTING.md) for the development setup, architecture overview, and checks to run, and [SECURITY.md](https://github.com/k8rthik/vimtg/blob/main/SECURITY.md) for reporting vulnerabilities privately.

## License and attribution

MIT, see [LICENSE](https://github.com/k8rthik/vimtg/blob/main/LICENSE).

vimtg is unofficial Fan Content permitted under the [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy). Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.

Card data and card-image links are provided by [Scryfall](https://scryfall.com) and used under Scryfall's [API and data guidelines](https://scryfall.com/docs/api); Scryfall is not affiliated with vimtg and does not endorse it. Deck-popularity data and recommendations come from [EDHREC](https://edhrec.com), which is likewise not affiliated with vimtg. vimtg is free and non-commercial: no payment, account, or subscription is required to use it or the card data it shows.

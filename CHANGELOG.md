# Changelog

All notable changes to vimtg are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
from 1.0.0 onward.

## [Unreleased]

### Changed (breaking key changes)

- Window keys moved to vim's `Ctrl-W` prefix, and the `S` prefix is gone:
  - `Sv` -> `Ctrl-W v` (vertical split, prompts for a deck)
  - `Sh` -> `Ctrl-W s` (horizontal split)
  - `Ss` -> `Ctrl-W w` / `Ctrl-W W`, and `Ctrl-W h`/`j`/`k`/`l` focus by
    direction (the pane is right of a vertical split, below a
    horizontal one)
  - `Sc` -> `Ctrl-W c` / `Ctrl-W q`; `Ctrl-W o` closes every window but
    the editor. Ctrl-W works from the editor and from a focused pane.
- Panes moved to a `Space` leader, and they toggle:
  - `Sa` -> `Space a` (analytics pane; `Space a` again closes it)
  - `Sr` -> `Space r` (EDHREC pane; `Space r` again closes it)
  - `Sd` -> `Space h` (sample hand overlay)
- Which-key menus are titled by their prefix (`window`, `leader`, `go`,
  `delete` ...) instead of "Next".

### Fixed

- In a focused pane `q` closes the pane instead of starting a macro
  recording in the editor, and `Esc` returns to the editor leaving the
  pane open. `g` sequences (`gh`, `g?`, `gc`) reach the editor instead of
  the pane: `gh` in the EDHREC pane no longer switches tab. The pane hint
  bars name `q` and `Esc`.
- The which-key popup after an operator shows that operator's motions:
  `dg` (on the way to `dgg`) no longer shows the `g` menu. The `q` menu
  no longer offers "stop recording" when nothing is recording.
- The editor and the deck parser now read every card line through one
  grammar, so the card under the cursor is always the card validation,
  analytics and export see: a pasted `(ZEN) 126 *F*` printing suffix is
  dropped from the name in the editor too, a line with tags but no name
  (`3  #tag`) or only a comment after the quantity (`4   // note`) is
  not a card to either, and `Hazmat Suit (Used)` keeps its name.
- A bare MTGO-style `Sideboard` line zones the cards after it as
  sideboard in the editor as well, not only in validation and export.
- A visual selection no longer outlives its mode: after `i`, a `/`
  search or an ex command from visual mode, the next `dd`/`yy`/`+`/`-`
  acts on one line again instead of the old selection.
- `:[range]g` and `:v` honour their range (`:1,5g/x/d`, `'<,'>g/x/d`)
  instead of running over the whole deck.
- `3x` deletes three card lines as one change (one `u`, every line in
  the register), as in vim. `dj` on the last line and `dk` on the first
  delete nothing. `+` stops at 999 copies. `.` on a selection leaves
  visual mode like the change it repeats.
- Marks follow cards added with `o`/`O` above them and lines moved with
  `:m`.
- `i` on a line inside a `CMD:`/`SB:`/`VS:` block keeps its indentation
  (un-indenting silently rezoned it and every line below); `i` then
  Enter on an untouched line no longer dirties the deck.
- Tab in the `/` prompt no longer rewrites the pattern as an ex
  command. A card search that was cancelled or confirmed never inserts
  a stale result or reopens the overlay when its worker finishes late.
- Restoring a history snapshot identical to the saved file does not
  mark the deck modified; `:layout` toggles back to type for a deck
  with no categories; the which-key tooltip hides when a paste cancels
  a pending operator; `9999p` is one insert.
- Sideboard plans board a card split over two lines (`2 Bolt @burn` +
  `2 Bolt @reach`) correctly in `:hand`, `vimtg hand` and plan
  previews, and plan lines match names the way validation does
  (`Fire/Ice` is `Fire // Ice`) and follow renamed cards on import.
- Cherry-pick and rebase no longer double a card split over two lines;
  merging a branch brings in the sideboard plans only that branch has.
- No false "outside commander color identity" errors while a partner
  commander's name is unknown. The free mulligan applies to `EDH`,
  `cEDH`, `Standard Brawl` and the other format aliases. New decks in
  every commander-style format (oathbreaker, duel, pauper commander)
  start with a `CMD:` block.
- Analytics count artifact lands and land creatures with the lands in
  the type breakdown. A headerless pasted list whose first group is a
  lone leader no longer gets a 59-card sideboard. `:import` of a file
  with a byte-order mark keeps vimtg layout; a Moxfield deck with a
  null quantity imports instead of failing.
- An empty or mis-shaped Scryfall download is an error that keeps the
  existing card data, instead of emptying the card table and being
  reused as a fresh cache for a week. A feed listing one card twice
  stores it once.
- Search queries that used to crash the overlay or `vimtg search`
  (`c:²`, huge counts, `/a{99999999999}/`, dozens of `-`, hundreds of
  nested parentheses or terms) are reported as syntax errors.
- Deck history survives a malformed snapshot timestamp; a recovery copy
  is found for a deck path with undecodable bytes; an unreadable
  category history or a config directory that is a file fall back to
  defaults with a warning.
- Opening an unreadable deck from the greeter shows an error there
  instead of quitting vimtg.
- `:w dir/` (or `:w` of an existing directory) is refused with E502
  instead of writing a hidden `dir/.deck`.
- Failed writes (`:w`, `vimtg new -o`, `vimtg convert -o`) name the
  target file, not an internal temp file.
- `vimtg new`/`convert` with `-o` pointing at a directory say so,
  instead of suggesting `--force`.
- `vimtg search -n` rejects 0 and negative limits (a negative one used
  to mean "unlimited").
- `vimtg validate`/`hand` call a corrupt card database unreadable
  rather than missing, and work without card data when the data
  directory cannot be created. `vimtg sync` no longer says it is
  "running without card data" when it cannot open the database.
- `*`/`#` messages show the card name instead of the internal regex.
- A sideboard-plan line with no card name (`-1 #tag`) is reported as
  unreadable instead of being saved back as `-1 `.
- A `:map` remap applies only where a command starts, so mapping `s` no
  longer breaks `zs` or a `"s` register name. `:map` refuses a key
  sequence such as `gb` (E474), which could never fire.
- `qA` appends to macro `a` instead of replacing it, and `@A` plays it,
  as in vim.
- An edit that section cleanup undoes again (`:t$` on the trailing blank
  line) no longer leaves an empty undo step or marks the deck modified.
- Rapid `+`/`-` fold into one undo step only on the same card: `+ j +`
  then `u` reverts just the second card. `u` and `Ctrl-R` move the
  cursor to the line they changed, as in vim.
- `/`, `?`, `n`, `N`, `*` and `#` wrap all the way round to the cursor
  line when it is the only match, instead of saying "Pattern not found",
  and a search that wraps says "search hit BOTTOM, continuing at TOP" as
  in vim.
- The greeter's `s` runs the same card sync as `:sync` and the automatic
  one, so it can no longer start a second download while one is running.
- The new-deck prompt accepts `Ctrl-U` and `Ctrl-W` like the other
  prompts, so a name prefilled from the file name can be cleared before
  typing.
- A deck that has never been written no longer shares one history with
  every other new deck: `:commit`, `:checkpoint`, `gh` and the other
  history commands say `E32: No file name` until the first `:w`.
- `:clipboard vimtg` copies the deck exactly as written, layout and
  comments included, the same text as `:export vimtg`.
- `:help` opens a command's topic under any alias (`:help exp`,
  `:help goldfish`), and `:dtag` / `:duntag` have topics. The README,
  `docs/commands.md`, and `docs/keybindings.md` now match the code on
  `:stats` (a one-line summary), `:dtag` / `:duntag` (deck-level
  `// Tags:`), `ZZ` (`:x`), mark ranges, `:g` sub-commands, the keys
  that are safe to `:map`, and the greeter's `R`.

## [1.0.0rc1] - 2026-10-10

### Added

- New-deck wizard: a deck with no cards and a blank name or format asks
  for both (`Tab` completes formats, `Esc` skips); commander and brawl
  answers add a `CMD:` block. The first `:w` of an unnamed deck names
  the file after `// Deck:`.
- First-run help: `:help` opens on a GETTING STARTED section, the idle
  hint reads `F1 help | o add card | i edit line | :w save | :q quit`,
  and empty decks show a tips panel (`:tips`, `:tips off`, `:tips on`).
- `:messages` (`:mes`) lists the last 100 messages, including pop-up
  notices (card sync failures, database recovery, config warnings);
  `:messages clear` empties it.
- The status line shows `recording @a (q stops)` while a macro records.
- Sample hand: `:hand [seed=N]` (`Sd`) and `vimtg hand` draw an opening
  seven with London mulligans, draw-next and reshuffle, plus land-count
  odds by turn on the play and draw. The active sideboard plan is used.
- Commander decks show a Game Changer count and an estimated bracket in
  the analytics pane and in `vimtg validate` (informational only).
- Search syntax shared by the `o`/`O` overlay, `:search` and
  `vimtg search`: `-` negation, `or`, parentheses, quoted phrases,
  `!"Exact Name"`, `/regex/` on name/type/oracle, `c:`/`id:` with every
  comparison and colour words (`boros`, `esper`), `mv`/`pow`/`tou`/
  `usd`/`eur`/`tix` comparisons, `r:`, `set:`, `f:`/`banned:`/
  `restricted:`, `kw:`, `m:` and `is:`/`not:`. See `docs/search.md`.
- Search additions: `produces:`, `is:permanent`/`spell`/`hybrid`/
  `phyrexian`, field-to-field comparisons such as `pow>tou`, back-face
  power and toughness, `order:`/`direction:`; `kw:partner` also finds
  "Partner with", and typographic quotes match straight ones. `year:` and
  `date:` are reported as unsupported.
- `:search [query]` opens the card search overlay pre-filled with the
  query, and `:help search` describes it.
- `:sync` / `:sync!` download card data in the background with progress
  in the status line, which also shows how old the card data is.
- `:clipboard` copies through the system clipboard tool (pbcopy,
  wl-copy, xclip, xsel, clip.exe) or OSC 52. Pasting a decklist in
  normal mode adds it as one undo step; bare `:import` reads the
  clipboard; the greeter opens a pasted decklist.
- Ex commands `:{n}`, `:$`, `:e[!] [file]`, `:[range]d [x]`,
  `:[range]y [x]`, `:[range]m {n}`, `:[range]t {n}` (`:co`), `:undo`,
  `:redo`, `:reg`, `:marks`, `:recover` / `:recover!`, `:saveas`.
- Unsaved work is kept as a recovery copy on Ctrl-C, Ctrl-Q, `:home`,
  SIGHUP and SIGTERM (`:q!`, `ZQ`, `:e!` and `:home!` discard it).
  Recovery copies are per deck path, and the greeter lists orphaned ones
  (`R`).
- `:` and search prompts keep a persisted Up/Down history and support
  `Ctrl-W`, `Ctrl-U`, `Ctrl-B`/`Ctrl-E` and Left/Right editing.
- `zz`/`zt`/`zb` scroll; `"_` is a black-hole register and `"+`/`"*`
  copy to the system clipboard; `ZZ` / `ZQ` run `:wq` / `:q!`.
- Formats: standardbrawl, oathbreaker, paupercommander, duel,
  premodern, timeless, penny, explorer, alchemy, and gladiator. Format
  names are case-insensitive and accept the aliases search accepts
  (`EDH`, `PDH`, `Historic Brawl`). `vimtg validate --strict` fails on
  warnings.
- `:export fmt` with no file copies the export to the clipboard;
  `:export!` overwrites an existing file.
- `vimtg convert` lists the lines it could not import; `:import`
  reports how many were skipped.
- `python -m vimtg` is guarded by `if __name__ == "__main__"`, so importing
  `vimtg.__main__` no longer launches the CLI.
- Project hygiene for 1.0: `CONTRIBUTING.md`, `SECURITY.md`, issue and pull
  request templates, Dependabot, and this changelog.
- Package metadata for PyPI: readme, authors, project URLs, classifiers, and
  keywords. Python 3.14 is supported and tested.
- vimtg is MIT licensed: a `LICENSE` file ships in the sdist and the wheel,
  and the package metadata declares `License-Expression: MIT`.
- The README credits Scryfall (card data) and EDHREC (recommendations), says
  neither is affiliated with vimtg, and carries the Wizards of the Coast Fan
  Content Policy notice.

### Changed

- **Keys:** in the editor `?` is backward search (`F1` or `:help` opens
  help, `g?` the quick-reference panel); `n`/`N` repeat the last search
  in the same/opposite direction; `*`/`#` search for the card under the
  cursor. Other screens still use `?` for help.
- **Operators:** `dw`/`cw` change one card, `db` deletes the card above,
  `d}`/`d{` stop at the section boundary, and `d8G`/`y5G` stop at the
  given line (`gg` takes a count). `.` repeats `o`/`O`/`c` with their
  card, puts, tags, categories, comments, `i`, `:s` and visual changes.
  Visual `x`, `+`/`-`, `z` zone moves and `zi`/`zo` act on the whole
  selection.
- `:s` is a case-insensitive regex like `/` (`&` and `\1` in the
  replacement, `I` flag for case); `:g`/`:g!` run `d`, `p`, `y [x]` and
  `s///`. `zc` is refused outside commander formats.
- `v`/`V` toggle off with the same key and switch kind with the other.
  `u` undoes one change at a time; only `+`/`-` bursts merge.
- Brawl is the 100-card format. Commander eligibility follows CR 903.3
  (Vehicles and Spacecraft with P/T, "can be your commander",
  Backgrounds; planeswalkers in Brawl, Oathbreaker signature spells),
  companions must fit the commander's colour identity, and copy limits
  honour "any number" / "up to N" oracle text. An oversized sideboard is
  an error.
- Card names resolve by full name or any face, ignoring case, accents,
  ligatures and separators ("Stomp", "Fire/Ice", "Aether Vial").
- Mana analytics: MDFC spells count as spells, fetch lands and
  any-colour lands count as sources, and the commander is included;
  the land recommendation follows Karsten's fits. Hybrid symbols ask for
  whichever colour the lands cover best, Phyrexian and `{2/W}` symbols
  never raise a source requirement, and fetch lands count only for
  colours of lands in the deck they can find. Split cards count both
  halves' pips, judge requirements per half, and use the cheaper half for
  the curve. `:stats` uses and names the configured price source.
- Validation: a companion counts toward the 15-card sideboard, and an
  Oathbreaker without a Signature Spell is an error.
- Imports: MTGO and Arena files use one decklist parser (`Nx`
  quantities, section headers, printing suffixes such as
  `(SET) 123`), Archidekt categories place zones, and BOM/CRLF files
  are accepted. Imports normalise names to each card's official name,
  count copies per card, and are laid out like a new deck (`// Deck:`,
  `// Format:`, zone blocks); a headerless Commander list puts the
  commander in the command zone; bare `Card` lines are one copy. URL
  imports carry the site's format and Moxfield signature spells.
- Exports write official card names: the front face for double-faced and
  adventure cards, `A // B` for split cards, the full name in CSV.
  `vimtg convert` resolves names against the synced card database, and
  `vimtg -> vimtg` copies the deck unchanged.
- `:w` refuses to overwrite another existing file or a deck changed on
  disk since it was read (`:w!` overrides); `vimtg new` refuses to
  overwrite without `--force`; `vimtg missing.deck` opens an empty deck
  bound to that path. `:export` refuses an existing file (E13) and never
  overwrites the open deck; `vimtg convert -o` refuses an existing file
  without `--force` and never overwrites its input.
- Every ex command that changes the deck marks it modified and is one
  undo step (`:sort` was not undoable); `cc` plus the new card is one
  step. `:x`/`ZZ` do not rewrite an unmodified deck, and `:w` notices a
  deck file deleted on disk.
- `:set` and the `:config` screen edit `config.toml` in place, keeping
  comments and layout.
- Saving no longer writes empty metadata lines the file never had.
- The greeter's recent decks include decks from any directory.
- Below 30x8 the terminal shows a "too small" notice instead of a
  garbled layout.
- The package version is single-sourced from `vimtg.__version__`;
  `pyproject.toml` no longer carries its own copy.
- Runtime dependencies are capped below their next major release
  (`textual<9`, `click<9`, `httpx<1`, `rich<16`); the minimums are now
  Textual 2.0 and click 8.2 (the oldest releases the test suite passes on).
- CI runs on Linux, macOS, and Windows with Python 3.12, 3.13 and 3.14,
  enforces 92% coverage, tests the lowest supported dependency versions,
  and builds and smoke-tests the wheel. The test suite can no longer
  reach the network.
- README rewritten for end users (install, quickstart, network and privacy);
  contributor material moved to `CONTRIBUTING.md`.
- First 1.0 release candidate: the PyPI classifier is now
  "Development Status :: 5 - Production/Stable", and `SECURITY.md` lists
  the 1.0 series as supported.

### Fixed

- Unexpected errors in the editor no longer close it: the buffer is
  written to a recovery file and `:recover` offers it on reopen. Two
  decks with the same file name no longer share a recovery copy.
- Crashes from undo/redo past the buffer end and from `v` in visual
  mode; opening a hand-written deck no longer marks it modified.
- Re-syncing card data replaces the table in one transaction, so no
  stale duplicate printings remain; transform and modal DFCs get their
  face colours.
- A damaged card database is backed up (`cards.db.corrupt-<time>`) and
  rebuilt with the readable history instead of failing to start.
- Fast typing in card search no longer fails on a shared database
  connection; unknown search keys and bad values are reported by name.
- Stale split and multi-face card rows force one re-sync (schema v2), so
  split-card costs and back-face power/toughness are right.
- Card search with no matches says "No matches" instead of showing
  nothing.
- Long card names are cut with an ellipsis instead of running into the
  mana cost.
- A wrong-shaped `[keybindings]` table or a wrong-typed setting in
  `config.toml` no longer crashes startup: each bad entry is skipped and
  reported.
- `vimtg search "mv>"` reports the incomplete term instead of printing
  "No cards found."; `vimtg --help` shows the whole search summary.
- `config.toml` and decks are written atomically; an unparseable
  `config.toml` is backed up and never overwritten.
- Clearer sync errors (offline, proxy, TLS interception) and Scryfall
  rate-limit backoff; CLI file and database errors exit cleanly with a
  hint.

## [0.8.0] - 2026-10-09

### Added

- Sideboard plans: `VS:` blocks in the deck file are parsed, validated,
  serialized, and versioned; edit them in the buffer with `mi`/`mo`, `:plan`,
  and `]v`/`[v`; they render with `-x +y` headers, signed entries, and delta
  cells.
- `:export guide` and `vimtg guide [--markdown]` print a sideboard guide.
- Card counts on headers: `DCK: (60)`, `// Creatures (12)`,
  `// Deck: Burn · 60/15 cards` (rendered only, never written to disk).
- Mouse-wheel and trackpad scrolling in the deck view, EDHREC, and analytics
  panes.
- Floating, lazy.nvim-style history overlay (`gh` / `:history`) with a
  working-copy panel, scrollable diff and stats, full merge graph, and branch
  delete.
- `n`/`N` and `H`/`M`/`L` motions.
- Argument completion for `:layout`, `:sort`, `:filter`, and `:category`;
  shell completion for `vimtg new --format`.
- `vimtg --version`; User-Agent strings carry the package version.

### Changed

- One navigation vocabulary on every screen (`j`/`k`, `gg`/`G`, Ctrl-D/U,
  wheel); `q`/Esc close and `?`/F1 open help everywhere; `z` is the zone
  prefix and `m` is marks only.
- The inline help panel scrolls like the help screen.
- `:g`/`:v` match card lines in every zone.
- `vimtg search` and the advanced search honour filter syntax, the colour
  filter, and `search_limit`.
- Category edits re-file the card under its new category.

### Removed

- `h`/`l`/`0`/`$` motions (the cursor has no column) and the
  documented-but-unbound `a` key.

### Fixed

- The deck view windows by rendered rows, so an expanded card under the
  cursor is never clipped.
- Invisible typing in `/` search, `1G`, register-name capture, and the config
  screen's Ctrl-C bypassing the discard guard.

## [0.7.0] - 2026-08-31

### Added

- Vim-style invocation: `vimtg burn.deck` opens the editor.
- Block style (`DCK:`/`SB:`/… zone blocks) is the default deck layout.
- Autocomplete for the `// Format:` field; unknown formats are surfaced.
- Import from Moxfield, Archidekt, ManaBox, Deckstats, TappedOut, and
  MTGGoldfish URLs, and from MTGO `.dek` files; the greeter's `[i]` action
  takes a file path or deck URL.
- Live analytics pane (`:analytics` / `Sa`).
- A count on `o`/`O` sets the number of copies (`4o`).

### Changed

- Card adds follow the cursor's zone; the cursor follows the inserted card.
- Buffer edits are constant-time despite zone-block reclassification.

### Fixed

- `o`/`O` on a metadata line opens below the block, never inside it.
- `md` in a category deck joins (or creates) the Uncategorized section.
- Scratch-line lifecycle for `o`/`O` blanks; inserts from visual mode.
- Section cleanup, `:sort` zones, ranges, and round-trip issues from an audit.

## [0.6.0] - 2026-08-15

### Added

- Plain-text deck editing: metadata scaffold, card comments, and a
  maybeboard zone.
- Format-aware validation with live gutter signs.
- Persistent version control: merge-parent history graph, merges,
  fast-forwards, rebases, and cross-deck merges; `:branch` and `:checkpoint`
  use it, plus new `:merge` and `:rebase`; interactive merge-conflict
  resolution.
- Categories, a configurable sort order, automatic card-data sync, and split
  panes.
- Commander and companion zones, with Python-style `CMD:` blocks for
  commanders and partners and a `DCK:` block header for the main deck.

### Fixed

- Card search was silently empty for non-canonical `// Format:` values.
- Search uses the deck's declared format.
- A literal `q` is recorded inside macros.
- Sections whose only cards are maybeboard lines are kept.
- Corrupt card JSON degrades gracefully; the anchor mark moves to the first
  pasted row.

## [0.5.0] - 2026-08-05

### Added

- Real macro recording and playback.
- `:map`/`:unmap` drive the key remapper, including multi-character targets.
- The tag filter works end to end.
- Seven previously inert settings are wired up.

### Fixed

- Missing command modules are registered; FTS5 queries are escaped;
  duplicate inserts no longer lose data.
- Command errors are shown distinctly in the UI.
- Config loading, VCS/SQLite paths, and parsing edge cases are hardened.
- Card sync integrity, CLI network errors, and a non-blocking greeter sync.
- Help, which-key, and screen hints match the real keymap.

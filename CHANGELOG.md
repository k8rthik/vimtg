# Changelog

All notable changes to vimtg are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
from 1.0.0 onward.

## [Unreleased]

### Fixed

- The editor and the deck parser now read every card line through one
  grammar, so the card under the cursor is always the card validation,
  analytics and export see: a pasted `(ZEN) 126 *F*` printing suffix is
  dropped from the name in the editor too, a line with tags but no name
  (`3  #tag`) or only a comment after the quantity (`4   // note`) is
  not a card to either, and `Hazmat Suit (Used)` keeps its name.
- A bare MTGO-style `Sideboard` line zones the cards after it as
  sideboard in the editor as well, not only in validation and export.

### Fixed

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

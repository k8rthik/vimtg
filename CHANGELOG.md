# Changelog

All notable changes to vimtg are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
from 1.0.0 onward.

## [Unreleased]

### Added

- `python -m vimtg` is guarded by `if __name__ == "__main__"`, so importing
  `vimtg.__main__` no longer launches the CLI.
- Project hygiene for 1.0: `CONTRIBUTING.md`, `SECURITY.md`, issue and pull
  request templates, Dependabot, and this changelog.
- Package metadata for PyPI: readme, authors, project URLs, classifiers, and
  keywords.

### Changed

- The package version is single-sourced from `vimtg.__version__`;
  `pyproject.toml` no longer carries its own copy.
- Runtime dependencies are capped below their next major release
  (`textual<9`, `click<9`, `httpx<1`, `rich<16`); the minimums are now
  Textual 2.0 and click 8.2 (the oldest releases the test suite passes on).
- CI runs on Linux, macOS, and Windows with Python 3.12 and 3.13, enforces
  92% coverage, tests the lowest supported dependency versions, and builds
  and smoke-tests the wheel. The test suite can no longer reach the network.
- README rewritten for end users (install, quickstart, network and privacy);
  contributor material moved to `CONTRIBUTING.md`.

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

[Unreleased]: https://github.com/k8rthik/vimtg/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/k8rthik/vimtg/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/k8rthik/vimtg/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/k8rthik/vimtg/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/k8rthik/vimtg/releases/tag/v0.5.0

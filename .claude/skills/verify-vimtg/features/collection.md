# Collection

`:collection file.csv` loads the cards a user owns from a ManaBox, Moxfield, Archidekt, or Deckbox export (any CSV with a name and a count column). The deck view then marks every card line the collection cannot cover with a dim `○` in the gutter, the card detail under the cursor ends with `owned N of M` or `not owned`, the analytics pane gains a `COLLECTION` block with the owned and missing totals and the cost to complete, and `:export missing` copies the shopping list. The path is saved to the `collection` setting and reloaded on every deck open. `vimtg missing deck.deck` prints the same list from the shell.

## Sub-features

- `coll-load` loads the CSV and reports `Collection: N cards (M unique) from file`.
- `coll-status` reports the loaded collection with bare `:collection`, or `No collection loaded (:collection path.csv)`.
- `coll-clear` forgets the collection with `:collection!`.
- `coll-sign` marks a card line with missing copies with `○`; a lint `✗` or `!` wins the cell.
- `coll-detail` ends the cursor card's expansion with `owned N of M` or `not owned`.
- `coll-analytics` shows the `COLLECTION` block (`Owned`, `Missing`, `To complete`) in the analytics pane.
- `coll-export` copies the missing cards with `:export missing`, or writes them with `:export missing file`.
- `coll-cli` prints the list and the total with `vimtg missing deck.deck [--collection file]`.
- `coll-reload` loads the configured file on deck open, warning once when it is missing.

## How to get to it (user POV)

- `:collection <path>`, `:collection`, `:collection!` on the command line (alias `:coll`).
- `:export missing [file]`.
- `Space a` or `:analytics` for the block.
- `vimtg missing deck.deck [--collection file.csv]` from the shell.
- `:config` and `:set collection=<path>` show and set the saved path.

## Driving it with vv

Preconditions:

- A fresh sandbox (`$V sandbox`), `$V tui start burn.deck`, `$V wait "F1 help" 20`. `collection.csv` is in `sandbox/decks/`, the TUI's working directory, so a relative path works.

- **Load.** `$V type ":collection collection.csv"; $V keys Enter; $V wait "Collection: 32 cards (7 unique) from collection.csv"; $V shot coll-load`. The message names the file; the deck view now shows `○` before `Monastery Swiftspear` (owns 2 of 4) and `Eidolon of the Great Revel` (owns none), and no sign before `Goblin Guide` (owns 4).
- **Status.** `$V type ":collection"; $V keys Enter; $V wait "Collection: 32 cards"; $V shot coll-status`.
- **Sign and detail.** `$V find "Eidolon of the Great Revel"; $V shot coll-detail`. The cursor line starts with `○`, and the expansion under `│` ends with a `not owned` line. `$V find "Monastery Swiftspear"; $V shot coll-detail-partial` ends with `owned 2 of 4`.
- **Lint wins the cell.** `$V find "Lightning Bolt"; $V keys C-a; $V shot coll-sign-lint`: the line shows `✗` (5 copies in modern), not `○`, although only 3 are owned. `$V keys u` restores it.
- **Analytics block.** `$V keys Space a; $V wait "Analytics pane open"; $V shot coll-analytics`. The pane shows `COLLECTION`, `Owned 32/67`, `Missing 35 (12 unique)`, and a `To complete` line (`$` total when the sandbox cards carry prices, else `unknown`). `$V keys Space a` closes it.
- **Export.** `$V type ":export missing"; $V keys Enter; $V wait "missing cards (13 lines)"; $V shot coll-export`. The message reports the clipboard copy (pbcopy, OSC 52, or that nothing worked). `$V type ":export missing missing.txt"; $V keys Enter; $V wait "Exported missing cards to missing.txt"`, then `cat .verify/current/sandbox/decks/missing.txt` shows `1 Lightning Bolt` first, a blank line, then `2 Rest in Peace`, `2 Kor Firewalker`, `2 Smash to Smithereens`.
- **Setting saved.** `grep collection .verify/current/sandbox/config/vimtg/config.toml` shows `collection = ".../sandbox/decks/collection.csv"`.
- **Reload on open.** `$V type ":q!"; $V keys Enter; $V tui start burn.deck; $V wait "F1 help" 20; $V shot coll-reload`. The `○` signs are back without typing `:collection`.
- **Clear.** `$V type ":collection!"; $V keys Enter; $V wait "Collection cleared"; $V shot coll-clear`. The `○` signs are gone and the setting is empty.
- **CLI.** `$V cli missing burn.deck --collection decks/collection.csv` (paths are relative to the sandbox root; `eval "$($V env)"` and `cd` to `decks` for a bare `collection.csv`). stdout starts `1 Lightning Bolt` and holds the sideboard block after a blank line; stderr is `Total to complete: ...`, exit `0`. Without `--collection` and with the setting cleared, exit `1` and stderr `No collection configured: ...`.

## Gotchas

- A missing configured file shows `Collection not loaded: collection file not found: ...` once on deck open; the deck stays editable. `:collection` with a bad path refuses and keeps the old collection.
- `○` never shows on a line that already has `✗` or `!`; check the card detail's `owned` line instead.
- `vimtg missing` puts the list on stdout and the total on stderr (`NN-cli.out` / `NN-cli.err`), so `| pbcopy` gets only the list.
- The sandbox's card set decides which missing cards are priced; `To complete` says `unknown` when none of them are.

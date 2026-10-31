# vimtg verification map

The maintained source for verifying vimtg's user-facing behavior. Read this index before driving the app, then follow the feature file that matches the change. `V=.claude/skills/verify-vimtg/scripts/vv` throughout.

## Baseline preconditions

- A fresh run: `$V sandbox`, then `$V doctor` reports `doctor: OK`, `cards: 84` and `tags: 67 (card, tag) rows`.
- Seed decks `burn.deck` (modern) and `krenko.deck` (Commander), and the collection export `collection.csv`, in the run's `sandbox/decks/`.
- The TUI started by this run (`$V tui start ...`). Never drive a vimtg you did not start.
- Offline: autosync and EDHREC are off in the sandbox environment.

## Driving conventions

- Start each recipe from a fresh `$V tui start <deck>` and `$V wait "F1 help" 20` unless it says otherwise. Restart the TUI between recipes so one recipe's edits never leak into the next.
- Text goes through `$V type`; keys through `$V keys` with tmux names (`Enter`, `Escape`, `C-a`, `Space`).
- Wait on the literal message or screen text named in the recipe before the next action. Do not sleep and hope.
- Jump to a card with `/<name>` + `Enter` rather than counting `j` presses: row numbers shift when lines are added.
- Mutations are proven on disk: `:w`, then read `.verify/current/sandbox/decks/<deck>`.

## Proof and skip reporting

- A `$V shot` before and after each action that changes state, plus the resulting message.
- File side effects: the saved deck's lines, or a second view (`$V cli info <deck>`, `$V cli validate <deck>`, or reopening the deck).
- Record the feature ID and entry point with each artifact (put the ID in the shot label: `$V shot edit-qty-after`).
- A path that needs the network (Scryfall sync, deck URL import, EDHREC data) is reported as not verified, with the reason. Never report it verified through a different path.

## Feature entry contract

Each feature file starts with an H1 and one paragraph on the user-visible behavior, then exactly four H2s in this order: `Sub-features` (short IDs), `How to get to it (user POV)` (every entry point), `Driving it with vv` (starts with `Preconditions:`, then labeled bullets pairing an action, its exact commands, and the observable result), and `Gotchas`. No implementation details.

## Features

- [Deck editing](./deck-editing.md) covers moving, quantities, delete/undo/repeat, adding cards through search, visual mode, ex commands, and saving.
- [Zones and sideboard plans](./zones-and-plans.md) covers sideboard/maybeboard moves, split counts, `VS:` plans, and legality signs.
- [Panes and windows](./panes-and-windows.md) covers the analytics pane, sample hand, EDHREC, `Ctrl-W w` focus, and the Space leader.
- [Collection](./collection.md) covers `:collection`, the `○` gutter sign, the owned line in the card detail, the analytics `COLLECTION` block, `:export missing`, and `vimtg missing`.
- [Version history](./version-history.md) covers `:w` snapshots, `:commit`, `:checkpoint`, and the history overlay.
- [Greeter, tutor, and CLI](./greeter-tutor-cli.md) covers the start screen, its `:` line, the tutor, import/export, and the shell subcommands.

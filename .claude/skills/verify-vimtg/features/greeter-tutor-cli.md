# Greeter, tutor, and CLI

`vimtg` with no arguments opens a greeter: new deck, file list, import, sync, recent decks, the tutor, help, and a small `:` command line. `vimtg tutor` opens a vimtutor-style lesson deck in a throwaway sandbox of its own. Shell subcommands validate, summarize, convert, search, and draw hands without opening the TUI.

## Sub-features

- `greet-menu` shows the menu keys (`n e i s r t ? q`) and runs them.
- `greet-cmdline` runs `:e <file>`, `:enew`, `:q`, `:help`, `:Tutor` from the greeter.
- `tutor-open` opens the lesson deck from `vimtg tutor`, the greeter's `t`, and `:Tutor` in the editor.
- `cli-validate` prints legality problems and exits non-zero on errors.
- `cli-convert` converts between `.deck` and other formats (`--to mtgo|arena|moxfield|archidekt|dek|mtga`).
- `cli-info` summarizes zones, format, and stats.
- `cli-search` searches the card database with the editor's syntax, `otag:` included, and notes when the oracle tags were never synced.

## How to get to it (user POV)

- `vimtg` (greeter), `vimtg tutor`, `vimtg <subcommand> --help`.
- `:home` from the editor returns to the greeter.

## Driving it with vv

Preconditions:

- A fresh sandbox. No TUI running (`$V tui stop` if one is).

- **Greeter.** `$V tui start; $V wait "Tutorial" 20; $V shot greet-menu`. The menu lists the keys and the recent/`.deck` files of `sandbox/decks`.
- **Greeter command line.** `$V type ":e burn.deck"; $V keys Enter; $V wait "F1 help"`. The editor opens `burn.deck`; the menu's `e` file list did not open.
- **Tutor from the greeter.** `$V tui stop; $V tui start; $V wait "Tutorial" 20; $V type t; $V wait "W E L C O M E" 20; $V shot tutor-open`. The lesson deck shows `Lesson 1: MOVING AROUND` below the welcome text.
- **Tutor from the shell.** `$V tui stop; $V tui start tutor; $V wait "W E L C O M E" 20`. Same screen.
- **Tutor leaves no trace.** `$V type ":q!"; $V keys Enter`, then `ls .verify/current/sandbox/decks` shows no `tutor.deck`: the tutor ran in its own temporary sandbox.
- **CLI validate.** `$V cli validate burn.deck` prints `ok (modern)` with exit `0`. After an edit that makes 5 copies and `:w`, it prints `burn.deck:<line>: error: Lightning Bolt: 5 copies (max 4 copies in modern)` with exit `1`.
- **CLI convert.** `$V cli convert burn.deck --to arena` prints Arena lines such as `4 Lightning Bolt` and a `Sideboard` block, exit `0`.
- **CLI info.** `$V cli info burn.deck` prints the zone counts (60 main, 7 side), format `modern`, and a `Stats:` row.
- **CLI search by oracle tag.** `$V cli search otag:ramp` prints Sol Ring, Arcane Signet, Mind Stone, Fire Diamond, Thought Vessel, Commander's Sphere, Mana Echoes and Skirk Prospector, exit `0`. `$V cli search -- -otag:ramp t:artifact` prints the other artifacts (Skullclamp, Coat of Arms, ...) and no Sol Ring. In a `VV_TAGS=0` sandbox, `$V cli search otag:ramp` prints `No cards found.` on stdout and `note: oracle tags not synced; run \`vimtg sync\` to download them` on stderr, exit `0`; its `00-sync.txt` ends with `Oracle tags skipped:` and the proxy error.

## Gotchas

- The greeter has no `Esc` action on its menu, and `Ctrl-C` only says to press `q`.
- Inside the tutor, its own sandbox replaces the run's XDG dirs for that process: a `:w` there writes to a temp dir that is deleted when the tutor exits. Prove tutor edits on screen, not on disk.
- `vimtg sync` and deck URL import need the network: report them as not verified here. `$V cli sync` would only reload the sandbox cache (cards and tags).
- CLI notes and errors go to stderr (`NN-cli.err`), command output to stdout (`NN-cli.out`).

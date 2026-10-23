# Deck editing

The editor shows a deck as text columns and edits it with vim keys: move with motions, change quantities, delete and undo, add cards through an inline card search that files each card under its type section, act on visual selections, run ex commands, and save to a plain `.deck` file.

## Sub-features

- `edit-move` moves by line, card, section, and search; the cursor card's rules text opens inline.
- `edit-qty` changes quantity with `+`/`-` and `Ctrl-A`/`Ctrl-X`, with counts.
- `edit-undo` deletes with `dd`/`x`, undoes with `u`, redoes with `Ctrl-R`, repeats with `.`.
- `edit-add` adds a card with `o`/`O` and a count (`4o`), through card search.
- `edit-visual` applies `d`, `+`, `-`, `zs` to a `V` selection.
- `edit-ex` runs `:s`, `:%s`, `:g/pat/d`, `:sort`, relative ranges like `:.,+1d`.
- `edit-save` writes with `:w`, writes a copy with `:w <file>`, quits with `:q`/`ZZ`.

## How to get to it (user POV)

- `vimtg burn.deck` in a shell opens the editor on that deck.
- From the greeter: `e` (file list), `1`-`5` (recent decks), or `:e burn.deck`.
- Inside the editor: `:e <file>`, `:enew`.

## Driving it with vv

Preconditions:

- `$V tui start burn.deck` and `$V wait "F1 help" 20` succeeded.
- `burn.deck` is the unmodified fixture (fresh sandbox).

- **Move to a card.** `$V find "Lightning Bolt"`. The highlighted line is `4   Lightning Bolt`, and the `│` lines under it show its type, `Lightning Bolt deals 3 damage to any target.`, and its set.
- **Change quantity.** `$V keys C-a`, then `$V shot edit-qty`. The line reads `5   Lightning Bolt` with `✗` in the gutter (5 copies is illegal in modern). `$V keys C-x` takes it back to 4 and the `✗` goes away.
- **Counted change.** `$V find "Skullcrack"; $V type "2+"`. The line reads `4   Skullcrack`.
- **Delete, undo, redo.** On Skullcrack: `$V type dd`. The line is gone. `$V type u` brings it back with the cursor on it. `$V keys C-r` deletes it again.
- **Add through search.** `$V find "Lightning Bolt"; $V type 2o; $V type helix; $V wait "Lightning Helix"; $V keys Enter; $V wait "Added 2x Lightning Helix"`. The new line `2   Lightning Helix` sits in the `// Instants` section. `$V keys C-o` returns the cursor to Lightning Bolt.
- **Visual selection.** `$V find "Lava Spike"; $V type "Vj+"`. Both `5   Lava Spike` and `5   Rift Bolt` show, each with `✗` (over 4 copies).
- **Ex command.** `$V find "Searing Blaze"; $V type ":s/Searing Blaze/Lightning Bolt/"; $V keys Enter; $V wait "1 substitution"`. Then `$V type u` restores `Searing Blaze`.
- **Save and prove it.** `$V type ":w"; $V keys Enter; $V wait "Written: burn.deck"; $V shot edit-save`. Then `grep -n "Lightning Helix\|Lava Spike" .verify/current/sandbox/decks/burn.deck` shows `2 Lightning Helix` and `5 Lava Spike`.
- **Write a copy.** `$V type ":w copy.deck"; $V keys Enter; $V wait '"copy.deck" written'`. `copy.deck` exists in `sandbox/decks/`, and the editor stays on `burn.deck`: the next `:w` says `Written: burn.deck`.
- **Quit.** `$V type ":q"; $V keys Enter; sleep 1; $V status` prints `exited 0`. With unsaved changes `:q` instead shows `E37: No write since last change (add ! to override)` and `$V status` stays `running`.

## Gotchas

- `q` in normal mode starts recording a macro (`recording @…` appears). It is not quit. `:q` is.
- `?` in the editor is a backward search, not help. Help is `F1`.
- `Ctrl-C` never quits: it acts like `Esc` and shows `Type :q and press Enter to exit vimtg`.
- After `o`, the card search needs the typed text to resolve before `Enter`: wait for the card name to appear in the results list, or `Enter` may add nothing.
- In a deck without type headers, `o` creates the section at the end of the main deck and the cursor jumps there. That is expected; `Ctrl-O` comes back.
- Rapid `+` presses on one card merge into one undo step; on different cards they don't.

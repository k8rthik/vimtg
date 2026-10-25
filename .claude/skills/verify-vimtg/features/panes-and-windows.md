# Panes and windows

Next to the deck, vimtg can show one side pane: live analytics or EDHREC recommendations. A sample-hand overlay draws opening hands. `Ctrl-W w` moves focus between the editor and the pane, as vim's "other window"; the panes hang off a `Space` leader and toggle.

## Sub-features

- `pane-analytics` toggles the analytics pane with `Space a` (`:analytics`).
- `pane-hand` opens the sample hand overlay with `Space h` (`:hand`).
- `pane-edhrec` toggles EDHREC recommendations with `Space r` (`:edhrec`), Commander decks only.
- `view-filter` opens the category filter prompt with `Space f` (`:filter expr`); non-matching cards dim and `Enter` on an empty prompt clears (`Filter cleared`).
- `pane-focus` moves focus into the pane and back with `Ctrl-W w`; `q` in the pane or `:close` closes it.

## How to get to it (user POV)

- Press `Space` and pause: the which-key menu titled `leader` lists `a`, `r`, `h`, `f`.
- Press `Ctrl-W` and pause: the `window` menu lists `w`.
- Ex commands `:analytics`, `:hand [seed]`, `:edhrec`, `:close`.

## Driving it with vv

Preconditions:

- `$V tui start burn.deck` and `$V wait "F1 help" 20` succeeded.

- **Open analytics.** `$V keys Space; $V type a; $V wait "Analytics pane open"; $V shot pane-analytics`. A pane appears beside the deck with the mana curve and type counts.
- **It follows edits.** `$V find "Lightning Bolt"; $V type 4+`, then `$V shot pane-analytics-live`. The pane's counts include the four new copies.
- **Close by toggle.** `$V keys Space; $V type a`. The pane is gone and the deck fills the width.
- **Sample hand.** `$V keys Space; $V type h; $V wait "Sample hand"; $V shot pane-hand`. A floating window lists seven cards. `$V keys Escape` (or `q`) closes it.
- **Focus the pane.** With analytics open, `$V keys C-w; $V type w; $V shot pane-focus`. The pane's left border turns orange; `$V keys C-w; $V type w` hands focus back (border grey). `$V type q` in a focused pane closes it.
- **:close closes the pane.** `$V type ":close"; $V keys Enter`. The pane is gone and the deck fills the width.
- **:q closes a window, not the app.** With the pane open, `$V type ":q"; $V keys Enter`. The pane closes and `$V status` stays `running`.
- **No second deck.** `$V type ":vsplit krenko.deck"; $V keys Enter; $V wait "E492"`. The message reads `E492: Not an editor command: vsplit krenko.deck`.
- **Filter by category.** `$V find "Lightning Bolt"; $V type gc; $V type burn; $V keys Enter`, then `$V keys Space; $V type f; $V type burn; $V keys Enter; $V wait "cards match"; $V shot view-filter`. Every card but the `@burn` ones is dimmed and the message reads `Filter: 1/N cards match (:filter! clears)`. `$V keys Space; $V type f; $V keys Enter; $V wait "Filter cleared"` clears it.
- **EDHREC is offline here.** `$V tui start krenko.deck`, then `$V keys Space; $V type r`. The pane says EDHREC lookups are disabled. Report `pane-edhrec` data as not verified (network).

## Gotchas

- The analytics pane opens without focus (it is a readout). `q` in the editor then starts a macro instead of closing it. Close with `Space a` again, or `Ctrl-W w` into the pane and `q`.
- `Space h` does not toggle: `Space` draws a card inside the hand overlay. Close it with `q`/`Esc`.
- The pane needs terminal width: at the 120-column tmux size it fits beside the deck; under 60 columns it hides until the terminal grows.

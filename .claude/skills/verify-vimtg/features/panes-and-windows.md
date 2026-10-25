# Panes and windows

Next to the deck, vimtg can show a live analytics pane, EDHREC recommendations, or a second deck in a split. A sample-hand overlay draws opening hands. Window keys follow vim's `Ctrl-W`; the feature panes hang off a `Space` leader and toggle.

## Sub-features

- `pane-analytics` toggles the analytics pane with `Space a` (`:analytics`).
- `pane-hand` opens the sample hand overlay with `Space h` (`:hand`).
- `pane-edhrec` toggles EDHREC recommendations with `Space r` (`:edhrec`), Commander decks only.
- `view-filter` opens the category filter prompt with `Space f` (`:filter expr`); non-matching cards dim and `Enter` on an empty prompt clears (`Filter cleared`).
- `pane-split` opens a second deck with `Ctrl-W v` / `Ctrl-W s` (`:vsplit`, `:split`); `Ctrl-W w` switches, `Ctrl-W c` closes.

## How to get to it (user POV)

- Press `Space` and pause: the which-key menu titled `leader` lists `a`, `r`, `h`, `f`.
- Press `Ctrl-W` and pause: the `window` menu lists `v s w c o`.
- Ex commands `:analytics`, `:hand [seed]`, `:edhrec`, `:vsplit <deck>`, `:close`, `:only`.

## Driving it with vv

Preconditions:

- `$V tui start burn.deck` and `$V wait "F1 help" 20` succeeded.

- **Open analytics.** `$V keys Space; $V type a; $V wait "Analytics pane open"; $V shot pane-analytics`. A pane appears beside the deck with the mana curve and type counts.
- **It follows edits.** `$V find "Lightning Bolt"; $V type 4+`, then `$V shot pane-analytics-live`. The pane's counts include the four new copies.
- **Close by toggle.** `$V keys Space; $V type a`. The pane is gone and the deck fills the width.
- **Sample hand.** `$V keys Space; $V type h; $V wait "Sample hand"; $V shot pane-hand`. A floating window lists seven cards. `$V keys Escape` (or `q`) closes it.
- **Split.** `$V keys C-w; $V type v`. The prompt asks for a deck: `$V type krenko.deck; $V keys Enter`. Both decks show side by side. `$V keys C-w; $V type w` moves focus (the focused pane gets the orange border); `$V type q` in the pane closes it.
- **:q closes a window, not the app.** With a split open, `$V type ":q"; $V keys Enter`. The split closes and `$V status` stays `running`.
- **Filter by category.** `$V find "Lightning Bolt"; $V type gc; $V type burn; $V keys Enter`, then `$V keys Space; $V type f; $V type burn; $V keys Enter; $V wait "cards match"; $V shot view-filter`. Every card but the `@burn` ones is dimmed and the message reads `Filter: 1/N cards match (:filter! clears)`. `$V keys Space; $V type f; $V keys Enter; $V wait "Filter cleared"` clears it.
- **EDHREC is offline here.** `$V tui start krenko.deck`, then `$V keys Space; $V type r`. The pane says EDHREC lookups are disabled. Report `pane-edhrec` data as not verified (network).

## Gotchas

- The analytics pane opens without focus (it is a readout). `q` in the editor then starts a macro instead of closing it. Close with `Space a` again, or `Ctrl-W w` into the pane and `q`.
- `Space h` does not toggle: `Space` draws a card inside the hand overlay. Close it with `q`/`Esc`.
- Panes need terminal width: at the 120-column tmux size a vertical split fits; narrower terminals fall back to a horizontal split.

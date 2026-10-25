# Ex commands

All commands are entered after `:` in normal mode. Most accept a vim-style
range prefix (`%` for the whole file, `5,10` for a line range, `.` for the
current line, `'a,'b` for marks). Any address takes `+N` / `-N` offsets, and
an offset alone counts from the cursor line: `.,+3d` deletes four lines,
`:+2` goes two lines down, `$-1` is the line before the last.

A command that lists things (`:registers`, `:marks`, `:tags`,
`:categories`, `:plans`, `:validate`, `:g/pat/p`, and the `tl`
key) prints on the command line when its output fits on one line, and
otherwise opens it in a floating pager, one entry per line, as vim's
more-prompt does (`q`/`Esc` close it; `:messages` keeps the output).

## File

| Command | Description |
|---------|-------------|
| `:w [file]` | Save deck. Without an argument, writes back to the loaded file; a deck with no file yet is written to the current directory as its `// Deck:` name slugified (`Mono-Red Burn` → `mono-red-burn.deck`, `-2`, `-3`… when taken; a random name when the deck is unnamed). Empty `// Deck:` / `// Format:` / `// Tags:` lines the file never had are not written. `:w file` writes a copy to `file` (`~` expands, `.deck` is appended when missing) and goes on editing the deck's own file, its unsaved changes still unsaved, as in vim (`"copy.deck" written`); a deck with no file yet takes the name instead. `:saveas file` switches to the new file. Refuses to overwrite another existing file (E13) or a file that changed on disk since it was read |
| `:w! [file]` | Save even over an existing file or outside changes |
| `:q` | Quit. Errors if there are unsaved changes (E37). With a split pane open it closes the pane instead (the other window, as in vim), from the editor or the pane |
| `:q!` | Quit, discarding changes (with a pane open: close the pane) |
| `:qa[!]` | Quit vimtg even with a pane open (also `:qall`, `:quitall`); `!` discards changes |
| `:wa` | Write the deck if it has changes (also `:wall`) |
| `:wqa` / `:xa` | Write the deck if it has changes, then quit vimtg (also `:wqall`, `:xall`) |
| `:wq` | Save and quit (with a pane open: save and close the pane). `:wq file` writes the copy, then quits only when the deck itself has no unsaved changes (E37 otherwise; `:wq!` quits anyway) |
| `:x` | Save if there are unsaved changes, then quit (also `ZZ`, `:xit`, `:exit`); with a pane open it closes the pane. A deck with no changes is not rewritten |
| `:saveas file` | Write the deck to `file` and edit that file from now on (alias `:sav`). `:saveas!` overwrites an existing file |
| `:home` | Return to the greeter (alias `:greeter`). Refuses with unsaved changes, like `:q`; `:home!` discards them |
| `:recover` | Load the recovery copy of this deck (`:recover!` deletes it). vimtg writes the copy under `~/.local/state/vimtg/recovery/` when it hits an internal error, and when the editor closes with unsaved changes, for example on `Ctrl-Q`, a closed terminal, or a dropped SSH connection. `:q!`, `ZQ`, `:e!`, and `:home!` discard the changes and the copy. Opening the deck again offers the copy; copies of unnamed buffers and deleted decks are listed on the greeter (`R`). The next successful `:w` removes the copy |
| `:e file` | Edit another deck in place of this one (`.deck` is tried when `file` has no suffix; a missing file opens as a new deck). Refuses with unsaved changes (E37) |
| `:enew[!]` | Edit a new, unnamed deck in place of this one (also `:ene`); the new-deck wizard asks for its name and format. Refuses with unsaved changes (E37); `!` discards them |
| `:e! [file]` | The same, discarding unsaved changes; `:e!` alone reloads this deck from disk |
| `:{n}`, `:$`, `:.` | Go to line `n` / the last line / stay (a range goes to its last line) |

## Editing

| Command | Description |
|---------|-------------|
| `:sort [field]` | Sort the current section. Fields: `name`, `cmc`, `type`, `color`, `qty`, `tag`, `category`, `power`, `toughness`, `rarity`, `price`. No field uses the `sort_order` setting (default `cmc`). `:sort!` reverses |
| `:%sort name` | Sort the entire deck alphabetically |
| `:s/pat/rep/[flags]` | Substitute. `pat` is a regular expression compiled exactly like `/` and `:g` (case-insensitive); an empty `pat` reuses the last search. In `rep`, `&` (or `\0`) is the whole match, `\1`-`\9` are groups, `\&` is a literal `&`. Flags: `g` (every match on a line), `I` (match case), `i` (ignore case, the default). `\/` puts a literal delimiter in either part. `.` repeats the last `:s` on the cursor line |
| `:%s/Bolt/Helix/g` | Substitute across the deck |
| `:[range]g/pattern/cmd` | Run `cmd` on every card line in the range (the whole deck by default; `'<,'>` from visual mode) matching `pattern`, in any zone (mainboard, sideboard, maybeboard, command zone, companion). Headers, comments, metadata, and plan entries never match. `cmd` is one of `d` (delete), `p` (list the matches), `y [x]` (yank into register `x`; `"A` appends), `s/pat/rep/[flags]` (substitute; an empty `pat` is the `:g` pattern) |
| `:v/pattern/cmd`, `:g!/pattern/cmd` | Inverse: run on every card line **not** matching |
| `:[range]d [x] [n]` | Delete lines (default: the cursor line) into register `x`. A number is a count, as in vim: `:d 3` deletes three lines from the cursor, `:5d a 2` lines 5-6 into `a`; with a range the count starts at its last line |
| `:[range]y [x] [n]` | Yank lines into register `x`, with the same count |
| `:[range]m {n}` | Move lines below line `n` (`0` = to the top, `$` = to the end, `.` = the cursor line, `+1` / `-2` relative to it, `'a` a mark) |
| `:[range]t {n}` | Copy lines below line `n` (also `:co`, `:copy`) |
| `:undo` / `:redo` | One undo / redo step (also `:u`, `:red`) |
| `:reg [x...]` | Show what the registers hold (also `:registers`, `:di`) |
| `:marks` | Show the marks with their line numbers |

Examples:

```
:g/Creature/d            delete every card line matching "Creature"
:g/^SB:/d                delete every SB:-prefixed sideboard card
:g/@ramp/s/^4/3/         cut every @ramp card to three copies
:g/bolt/y A              append every Bolt line to register a
:%s/Mountain/Plains/g    swap every Mountain for Plains
:%s/^(\d+) (.*)$/\2 x\1/ rewrite "4 Bolt" as "Bolt x4"
:1,20sort cmc            sort lines 1–20 by mana cost
:5,8m0                   move lines 5–8 to the top
:'a,'bd                  delete from mark a through mark b
:m+1 / :m-2              move the line down one / up one
:t-1                     copy the line above itself
```

Not supported, because the deck is line-oriented or the feature has no
deck meaning: `:normal`, `:j[oin]`, `:>`/`:<`, and `:r[ead]`.

## Search & navigation

| Command | Description |
|---------|-------------|
| `:noh` | Accepted for the vim habit (also `:nohlsearch`); vimtg draws no search highlight to clear |
| `:find pattern` | Jump to the next card matching `pattern` (also `/`; `?` searches backward; `n` / `N` repeat in the same / opposite direction) |
| `:search [query]` | Open the card database search overlay, like `o`, with `query` typed in ([syntax](search.md)); an empty search says "No matches", or `No matches legal in modern (3 more in other formats)` when the deck's format filtered the matches out; `Enter` on it closes the search with that message |

## Categories & layout

Categories are user-defined purpose labels — one per card (`@ramp`,
`@draw`, `@wincon`). The layout commands regroup the whole mainboard
under either card-type headers or `// @category` headers; each card
keeps its `@category` token, so toggling back and forth is lossless.

| Command | Description |
|---------|-------------|
| `:category name` (alias `:cat`) | Set the category on the current line (or range). Tab-completes in the `gc` prompt. In a category-grouped deck the card moves under its new `// @name` header (created if needed) |
| `:category!` | Clear the category from the line/range; in a category-grouped deck the card moves to `// Uncategorized` |
| `:categories` (alias `:cats`) | List categories with counts; `:categories name` lists that category's cards |
| `:layout type` | Regroup mainboard by card type (`// Creatures`, …) |
| `:layout category` | Regroup by category (`// @ramp`, …); uncategorized cards group last |
| `:layout` | Toggle between the two (also the `gl` key) |

In-group card order follows the `sort_order` setting
(`:set sort_order=cmc` by default).

## Splits & EDHREC

The editor supports one split pane beside (`:vsplit`) or below
(`:split`) the main deck view. It shows either another deck read-only —
compare a netdeck or an old version while editing — or EDHREC
recommendations for the deck's commander. `Ctrl-W w` switches focus
into the pane (`j`/`k` scroll or select, `h`/`l` switch tabs, `Esc`
returns).

| Command | Description |
|---------|-------------|
| `:vsplit deck` (alias `:vsp`, `:vs`) | Open another deck file side by side (read-only) |
| `:split deck` (alias `:sp`, `:hsplit`) | Same, stacked below |
| `:close` (alias `:only`) | Close the split pane |
| `:edhrec [type]` (alias `:rec`) | EDHREC recommendations for the commander(s) on the deck's `CMD:` lines |

`:edhrec` is Commander-only: the deck must declare `// Format: commander`
(or no format) and have a `CMD:` line; partner pairs use both names. The
pane has one tab per card type (Top, Creatures, Instants, Sorceries,
Artifacts, Enchantments, Planeswalkers, Battles, Lands) — the optional
argument jumps straight to one (`:edhrec creatures`). Each row shows the
inclusion rate and synergy score; `✓` marks cards already in the deck,
and `Enter` adds the selected card to the matching type section.
Responses are cached for 7 days under the XDG cache directory.

## Tags

| Command | Description |
|---------|-------------|
| `:filter expr` | Filter the view to cards matching the tag expression |
| `:dtag name...` | Add deck-level tags to the `// Tags:` metadata line, creating the line when the deck has none |
| `:duntag name...` | Remove deck-level tags from the `// Tags:` line. The emptied line stays, so `i` can refill it |

Filter expression grammar:

```
expr  := term ('|' term)*
term  := factor ('+' factor)*
factor := '-'? IDENT
```

So `core+staple-removal` means `(core AND staple) AND NOT removal`, while
`core|staple` is `core OR staple`. An empty expression clears the filter.

## Import / export

| Command | Description |
|---------|-------------|
| `:export fmt [file]` | Write the deck as `arena`, `mtgo`, `dek`, `moxfield`, `archidekt`, `vimtg`, or `guide` to `file` (`~` expands); with no file, copy it to the clipboard. `vimtg` is the text `:w` writes, so empty `// Format:`/`// Tags:` lines the file never had are left out |
| `:export! fmt file` | Same, overwriting an existing `file` (`:export` refuses with E13). The open deck's own file is never an export target |
| `:import[!] file` | Open `file` as a new unnamed deck in place of this one, as the greeter's import does (the open deck is left as it is on disk; the first `:w` names the new file after its `// Deck:` line), auto-detecting format. Refuses with unsaved changes (E37); `!` discards them. A vimtg deck comes in as written; other formats get `// Deck:` / `// Format:` lines and `CMD:`/`DCK:`/`SB:` blocks (type sections when card data is synced), with names normalised to each card's official name |
| `:import` | Same, with the decklist (or deck URL) on the system clipboard |
| `:clipboard [fmt]` | Copy the deck to the system clipboard in any `:export` format (default arena): pbcopy/wl-copy/xclip/xsel/clip.exe, else OSC 52 |

Pasting (your terminal's paste key) in normal mode adds the pasted
decklist to the deck as one undo step; in card search or on the `:`
line it inserts the text.

## Version control

vimtg keeps one linear chain of snapshots per deck, saved across
sessions. `:history` (or `gh`) opens a floating lazygit-style overlay
over the editor with Working copy, Snapshots, Diff, and Stats panels,
where snapshots can be tagged and restored. See
[keybindings.md](./keybindings.md#history-overlay-gh-history) for the
overlay keys.

| Command | Description |
|---------|-------------|
| `:history` (alias `:log`) | Open the history overlay (also `gh`) |
| `:commit "msg"` | Snapshot the current deck state |
| `:checkpoint name` | Commit the current state and tag it |

History belongs to the deck file, so a deck that has never been written
has none: `:commit`, `:checkpoint` and `gh` say `E32: No file name`
until the first `:w`. `:w` snapshots the deck as `auto: save`; a
`:commit` of the same deck right after names that snapshot instead of
adding a second one. Restoring a snapshot loads it into the editor and
records the restore as a new snapshot on top of the history.

## Analytics

| Command | Description |
|---------|-------------|
| `:stats` | Print a one-line summary on the command line: card count, average CMC, cards per type, and the total price with its source, e.g. `$12.34 (usd)`. Without card data it counts the card lines in each zone. For the curve, colors, and mana base, use `:analytics` |
| `:validate` | Check format legality: deck size, copy limits, sideboard rules, commander rules (exact deck size, singleton with oracle-text exceptions, no sideboard, eligible commander, ≤2 partners, color identity of the deck and the companion), and sideboard-plan consistency. The same report as `vimtg validate`: without card data it says legality was skipped (run `:sync`), and a Commander deck also gets its Game Changer count and estimated bracket |
| `:analytics` | Live analytics pane: curve, counts per type/zone/category, mana base with a suggested land count, Commander bracket estimate (Commander decks), draw odds (alias `:ana`, key `Space a`); with a plan active it shows the post-board deck. See [analytics.md](./analytics.md) |
| `:hand [seed=N]` | Sample-hand / goldfish overlay (alias `:goldfish`, key `Space h`): see below |

### Sample hand

`:hand` shuffles the main deck and draws an opening seven. Only
mainboard cards go into the library (respecting quantities); sideboard,
maybeboard, commander and companion cards stay out. A Commander deck
shows its commander in the command zone and draws from the 99. With a
sideboard plan active (`:plan`), the post-board deck is used.

| Key | Action |
|-----|--------|
| `n` / `Space` | Draw the next card |
| `m` | London mulligan: shuffle, draw seven, then owe one card to the bottom per mulligan (the first is free in Commander, Brawl, Oathbreaker and Pauper Commander) |
| `j` / `k` | Select a card in hand (`gg` / `G`, `Ctrl-D` / `Ctrl-U`, `Home` / `End` too) |
| `b` | Put the selected card on the bottom (after a mulligan) |
| `r` | Reshuffle and deal a fresh hand |
| `?` / `F1` | This topic / the full help |
| `q` / `Esc` | Close |

Drawing waits until the mulligan's cards are on the bottom, and a hand
cannot be mulliganed once kept (after a draw or a bottom). The overlay
shows the land count in hand and hypergeometric odds for a seven-card
hand: P(at least 1 land), P(at least 2 lands), and the chance of having
hit every land drop through turn N (N = 1 to 5) on the play and on the
draw. Lands are recognised from the card database (any card whose type
line contains Land); without one, only basic lands count.

`seed=N` (or just `N`) seeds the shuffle: the same seed and key presses
give the same hands. From the shell, `vimtg hand FILE [--seed N]
[--draws N] [--plan NAME]` prints a sample hand, any extra draws and
the same odds.

## Sideboard plans

A plan is a `VS: <matchup>` block at the end of the deck listing
`-N Card` (out of the mainboard) and `+N Card` (in from the sideboard)
lines — see [deck-format.md](./deck-format.md#sideboard-plans). One plan
is *active* at a time: `zo`/`zi` write into it, deck cards show their
`-N`/`+N`, the status line shows `vs Tron -4/+4` (with `!` when
unbalanced), and `:analytics` boards the deck with it.

| Command | Description |
|---------|-------------|
| `:plan <matchup>` | Activate the plan, creating its `VS:` block when new; the cursor moves to the header |
| `:plan` | Activate the next plan (wraps) |
| `:plan!` | Deactivate |
| `:plans` | List every plan with its `-out +in` totals (`*` marks the active one) |
| `:export guide [file]` | Write the plans as a Markdown sideboard guide |

Inside a plan block, `o` searches the deck's own cards and writes a
signed line (`+` for a sideboard card, `-` for a mainboard card), `+`/`-`
adjust a line's count, and `dd` removes it.

## Configuration

| Command | Description |
|---------|-------------|
| `:config` | Open the settings screen |
| `:set key=value` | Set an editor option and save it to `config.toml` (edited in place, comments kept); bare `:set` lists all |
| `:map key action` | Remap a normal-mode key for this session. A multi-key `action` is typed key by key, and one that starts with `:` runs as a command (`:map ; :w`). Bare `:map` lists the mappings. See [keybindings.md](./keybindings.md#remapping) |
| `:unmap key` | Remove a mapping |

Card data auto-syncs in the background when the local database is
missing or older than a week (`:set noautosync` turns this off; the
`vimtg sync` CLI command always works manually).

| Command | Description |
|---------|-------------|
| `:sync` | Download card data in the background; progress in the status line |
| `:sync!` | Same, re-downloading even when the cached bulk file is fresh |

## Help

| Command | Description |
|---------|-------------|
| `:help` | Open the help window on the overview (also `F1`; `g?` toggles the cheat sheet) |
| `:help cmd` | Open help for a specific command |
| `:messages` | Show the last 100 command-line messages and errors (alias `:mes`; `:messages clear` empties it). Messages vanish at the next key; errors stay up while you move the cursor |
| `:tips` | Show the getting-started tips panel (`Esc` hides it) |
| `:Tutor[!]` | Leave this deck for the tutor, a fresh lesson deck in an offline sandbox, like vimtutor (alias `:tutor`; the same as `vimtg tutor`). Unsaved changes need `!` |
| `:tips off` / `:tips on` | Stop / resume showing the tips under empty decks, which keep them through the first cards until the first `:w` (remembered across sessions) |

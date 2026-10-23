# Keybindings

Five rules hold everywhere in vimtg, so a key means one thing no matter
which screen is open:

1. **One navigation vocabulary.** `j`/`k` and the arrow keys move one
   line. `gg`/`G` and `Home`/`End` go to the top/bottom. `Ctrl-D`/`Ctrl-U`
   move half a page. The mouse wheel scrolls whatever is under it. A bare
   `g` never means "top".
2. **One dismissal vocabulary.** `q` and `Esc` close every auxiliary
   screen; `Esc` cancels an open prompt first. In the editor `Esc` exits
   the current mode and `q` is vim's macro key.
3. **One help vocabulary.** `F1` opens the full help on every screen.
   Outside the editor `?` opens help for the current screen; in the
   editor `?` is vim's backward search, so help there is `F1` or `:help`
   and the quick-reference panel is `g?`.
4. **Separated editor prefixes.** Each prefix has one job: `g` go, `t`
   tags, `S` splits, `z` zones, `m` marks, `'` jump to mark, `q`/`@`
   macros, `"` registers, `[`/`]` jumps.
5. **One source of truth.** The editor keys are declared in
   `src/vimtg/editor/keyspec.py`; which-key, the in-app help overview,
   and the drift tests read that table. Screen hint bars render from
   their own binding tables through one formatter.

Spelling used in every hint and in this file: `Ctrl-D`, `Ctrl-U`,
`Ctrl-R`, `Esc`, `Enter`, `Tab`, `Shift-Tab`, `Space`, `F1`, ranges as
`1-5`, placeholders as `{a-z}`.

## Editor

Everything below is normal mode unless flagged otherwise.

### Modes

| Key | Action |
|-----|--------|
| `i` | Edit the current line in place. On `// Key:` metadata lines only the value is editable; the `// Format:` value Tab-completes known formats |
| `A` | Add or edit the card's inline comment (`// …`); confirming empty text removes it |
| `o` / `O` | Add a card below / above: opens card search. The card joins the zone under the cursor (inside a `CMD:`/`SB:` block it lands there; in the mainboard it auto-files by type). A count sets copies: `4o` adds four. Inside a `VS:` plan block it writes a signed plan line |
| `v` / `V` | Visual / visual-line selection |
| `:` | Ex command line |
| `/` / `?` | Search forward / backward for a card (a regex, case-insensitive, like `:g` and `:s`). An empty pattern repeats the last one |
| `Esc` | Back to normal mode; cancels a pending key sequence (in normal mode it also hides the getting-started tips) |
| `F1` | Full-screen help (also `:help`) |
| `g?` | Toggle the quick-reference panel (`q`, `Esc`, or `?` closes it) |
| `ZZ` / `ZQ` | Save if there are changes, then quit (`:x`) / quit discarding changes (`:q!`) |

### Navigation

| Key | Action |
|-----|--------|
| `j` / `k` | Down / up, skipping blank lines |
| `gg` / `G` | First / last line; `{n}G` or `{n}gg` goes to line `n` (`1G` is line 1; `:{n}` too) |
| `w` / `b` | Next / previous card entry |
| `{` / `}` | Previous / next section |
| `[[` / `]]` | Previous / next section or plan header |
| `[v` / `]v` | Previous / next sideboard plan (activates it) |
| `Ctrl-D` / `Ctrl-U` | Half page down / up |
| `H` / `M` / `L` | Top / middle / bottom of the visible deck view (a count offsets `H` and `L`: `3H` is the third visible line). The scrolloff margin is respected, so the view does not move |
| `n` / `N` | Repeat the last search in the same / opposite direction (`n` after `?` goes backward), wrapping around the deck (back to the cursor line when it is the only match) with "search hit BOTTOM, continuing at TOP" |
| `*` / `#` | Search forward / backward for the card under the cursor (the whole name: `*` on Shock never stops on Shock Troops) |
| `zz` / `zt` / `zb` | Scroll the view so the cursor line is at the center / top / bottom; the cursor does not move |
| mouse wheel | Scroll three lines per notch, vim-style: the window moves and the cursor is dragged only when it would leave the screen |

Any motion takes a count: `10j`, `3w`, `2n`. The deck is line-oriented: there is no column cursor, so `h`/`l`/`0`/`$` are not bound.

As operator targets, `j`/`k`/`G`/`gg`/`Ctrl-D`/`Ctrl-U` are linewise and
include the line they land on; `w`/`b`/`{`/`}`/`[[`/`]]` are exclusive,
as in vim, and never eat the next section's blank line or header:

| Keys | Deletes |
|------|---------|
| `dw` / `3dw` | This card / this card and the next two |
| `db` | The card above (not the one under the cursor) |
| `d}` | From the cursor to the end of its section |
| `d{` | The cards above the cursor in its section |
| `d]]` | Up to, not including, the next header |
| `dG` / `d8G` | To the end of the deck / through line 8 |

### Editing

| Key | Action |
|-----|--------|
| `dd` / `yy` / `cc` | Delete / yank / change the card line (`cc` deletes, then opens card search) |
| `d` `y` `c` + motion | Operators compose with a motion: `dw` deletes this card entry, `d}` to the end of the section, `y5G` through line 5. Counts multiply: `2d3j` |
| `x` | Delete the card under the cursor (into the register); card lines only. A count deletes that many consecutive card lines as one change (`3x`, then one `u`) |
| `p` / `P` | Paste below / above; `3p` pastes three copies |
| `+` / `-` | Increment / decrement quantity; `-` at 0 deletes the line. Both keep zone prefixes, plan signs, `@category`, `#tags`, and comments |
| `.` | Repeat the last change (a count overrides the recorded one). Every edit repeats: operators, `c` together with the card it added, `o`/`O` with their card and copies, `p`/`P`, `+`/`-`, `x`, zone and plan moves, tags, categories, comments, `i`, and `:s` (on the cursor line). A change made on a visual selection repeats on as many lines from the cursor |
| `u` / `Ctrl-R` | Undo / redo, one change per `u`. Only a quick burst of `+` or `-` folds into one step |

### Zones (`z` prefix)

| Key | Action |
|-----|--------|
| `zs` / `zm` / `zd` | Move the card to the **s**ideboard / **m**aybeboard / main **d**eck |
| `zc` / `zp` | Move the card to the **c**ommand zone (`CMD:`) / com**p**anion slot (`CMP:`) |
| `zo` / `zi` | Board the card **o**ut of / **i**nto the active sideboard plan (see `:plan`) |

A bare zone key moves every copy; a count splits: `2zs` moves two. Moves
keep the card's category, tags, and comment, merge into an existing line
in the target zone, and match the zone's block or prefix style.

The deck's format (`// Format:`, else the `default_format` setting)
is checked: `zc` is refused outside commander formats, which have no
command zone, and `zs` in a format without a sideboard (commander)
moves the card but warns. An unknown or missing format checks nothing.
`zz`/`zt`/`zb` scroll the view, as in vim.

### Marks, macros, registers

| Key | Action |
|-----|--------|
| `m{a-z}` | Set a mark (all 26 letters are available) |
| `'{a-z}` | Jump to a mark. Marks shift through inserts, deletes, puts, and zone moves |
| `q{a-z}` / `q` | Start recording a macro / stop recording; `qA` appends to macro `a` |
| `@{a-z}` / `@@` | Play a macro / replay the last one; `3@a` plays three times |
| `"{a-z}` | Use a named register for the next yank, delete, or put. `"A`-`"Z` append, `"0` is the yank register, `"1`-`"9` the delete history |
| `"_` | The black hole register: `"_dd` deletes without touching any register, so the next `p` still puts what was there |
| `"+` / `"*` | The clipboard register (one register, two names): a yank or delete also copies to the system clipboard via OSC52. `"+p` puts what was last yanked to it in this session (vimtg cannot read the system clipboard) |

### Visual mode

| Key | Action |
|-----|--------|
| `d` / `y` / `c` | Delete / yank / change the selection |
| `x` | Delete the selection (same as `d`) |
| `+` / `-` | Increment / decrement every card in the selection (`3+` adds three to each) |
| `zs` / `zm` / `zd` / `zc` / `zp` | Move every selected card to that zone |
| `zi` / `zo` | Board every selected card in / out of the active plan |
| `o` | Jump to the other end of the selection |
| `gc` / `gC`, `ta` / `tr` / `tt` | Category and tag prompts apply to the whole selection |
| `Esc` | Exit visual mode |

Each of these ends the selection and is one undo step. Motions extend
the selection; other keys act on the cursor line.

### Categories (`g` prefix)

| Key | Action |
|-----|--------|
| `gc` | Set the card's category (or the visual range). The prompt ghost-completes from this deck, previously used names, and presets; `Tab` accepts. In a category-grouped deck the card moves under its new header |
| `gC` | Clear the category; in a category-grouped deck the card moves to `// Uncategorized` |
| `gl` | Toggle layout: group by card type / by category |

`gg` (top), `gh` (history overlay), and `g?` (quick reference) share the prefix.

### Tags (`t` prefix)

| Key | Action |
|-----|--------|
| `ta` / `tr` / `tt` | Add / remove / toggle a tag (prompts) |
| `tf` | Filter the view by a tag expression (`core+flex`, `core|flex`, `-flex`) |
| `tl` | List tags with counts |
| `tc` | Clear the card's tags |
| `tn` / `tp` | Next / previous card sharing a tag with the cursor |

### Splits, EDHREC, analytics (`S` prefix)

| Key | Action |
|-----|--------|
| `Sv` / `Sh` | Open a **v**ertical / **h**orizontal split (prompts `:vsplit ` / `:split ` for a deck file) |
| `Sr` | EDHREC **r**ecommendations for the commander (`:edhrec`) |
| `Sa` | Live **a**nalytics pane (`:analytics`) |
| `Sd` | Sample hand: **d**raw an opening seven and goldfish (`:hand`) |
| `Ss` | **S**witch focus between the editor and the pane |
| `Sc` | **C**lose the pane |

While a pane is focused it uses the shared navigation keys (`j`/`k`,
`gg`/`G`, `Home`/`End`, `Ctrl-D`/`Ctrl-U`, wheel). The EDHREC pane adds
`h`/`l` (or `Tab`/`Shift-Tab`) to switch tabs and `Enter` to add the
selected card. `Esc` returns to the editor; `:` and `S` sequences pass
through; any other key refocuses the editor and runs there.

`Sd` opens the sample-hand overlay rather than a pane. In it, `n` or
`Space` draws, `m` takes a London mulligan, `j`/`k` select a card and
`b` puts it on the bottom, `r` reshuffles a fresh hand, and `q`/`Esc`
close it.

### Version control

| Key | Action |
|-----|--------|
| `gh` | Toggle the history overlay (see below) |

### Prefix map

| Prefix | Namespace | Keys |
|--------|-----------|------|
| `g` | go | `gg` `gc` `gC` `gl` `gh` `g?` |
| `t` | tags | `ta` `tr` `tt` `tf` `tl` `tc` `tn` `tp` |
| `S` | splits | `Sv` `Sh` `Sr` `Sa` `Sd` `Ss` `Sc` |
| `z` | zones & scroll | `zs` `zm` `zd` `zc` `zp` `zo` `zi`, `zz` `zt` `zb` |
| `m` / `'` | marks | `m{a-z}` `'{a-z}` |
| `q` / `@` | macros | `q{a-z}` `q` `@{a-z}` `@@` |
| `"` | registers | `"{a-z}` `"0` `"1`-`"9` `"_` `"+` `"*` |
| `[` / `]` | jumps | `[[` `]]` `[v` `]v` |
| `d` `y` `c` | operators | wait for a motion |

A mistyped sequence is dropped silently and the which-key popup closes.

### Card search (insert mode)

| Key | Action |
|-----|--------|
| typing | Updates the query ([search syntax](search.md)); results appear from two characters, or the error naming an unknown key or bad value |
| `Tab` / `Ctrl-J` / `Ctrl-N` / `Down` | Next result |
| `Shift-Tab` / `Ctrl-K` / `Ctrl-P` / `Up` | Previous result |
| `Enter` | Confirm (a duplicate in the same zone bumps its quantity) |
| `Esc` | Cancel; the scratch line is removed and the cursor restored |
| `Left` / `Right`, `Ctrl-B` / `Ctrl-E`, `Home` / `End` | Move in the query |
| `Ctrl-W` / `Ctrl-U` | Delete the word before the cursor / everything before it |

### Command mode

| Key | Action |
|-----|--------|
| `Tab` / `Shift-Tab` | Accept the completion and cycle forward / back |
| `Up` / `Down` | Recall older / newer history entries that start with what was typed |
| `Left` / `Right`, `Ctrl-B` / `Ctrl-E`, `Home` / `End` | Move the cursor / to the start or end |
| `Ctrl-W` / `Ctrl-U` | Delete the word before the cursor / everything before it |
| `Backspace` | Delete a character; on an empty line, leave the command line |
| `Enter` | Execute |
| `Esc` | Cancel |

The same keys edit the `/` and `?` search prompts. `:` and search keep
separate histories (200 entries each, duplicates collapsed), saved in
`~/.local/state/vimtg/cmdline_history.json` so they survive restarts.

Completion is fuzzy: `:so` matches `sort`, `:st` matches `sort` and `stats`.
After a space it completes the argument: `:layout ` offers `type` / `category`,
`:sort c` offers `category`, `cmc`, `color`, `:filter core+fl` completes the
deck tag after the last `+`, `|`, or `-`, and `:cat dr` completes a category
from the deck, your history, or the presets.

## Screens

Every screen accepts the shared vocabulary:

| Key | Action |
|-----|--------|
| `j` / `k` / `Down` / `Up` | Move one line or entry |
| `gg` / `G`, `Home` / `End` | Top / bottom |
| `Ctrl-D` / `Ctrl-U` | Half page |
| mouse wheel | Scroll the list or panel under the pointer |
| `q` / `Esc` | Close (`Esc` cancels an open prompt first) |
| `?` / `F1` | Help for this screen / full help |

### Greeter

| Key | Action |
|-----|--------|
| `n` / `e` / `i` / `s` / `r` | New deck (asks for name and format) / open a file / import a file or URL / sync cards / recent decks (from any directory) |
| `1`-`5` | Open the nth recent deck listed |
| `R` | Unsaved buffers left by an earlier session (listed only when there are any). `Enter` opens one, `d` discards it |
| `?` / `F1` | Help overview (scrolls with the shared keys) |
| `q` | Quit vimtg. `Esc` does nothing on the menu; in a sub-mode it goes back |
| lists | Shared navigation, `Enter` open, `n` new deck, `q`/`Esc` back |
| import | Type or paste a path or URL, `Enter` import, `Esc` back |

### New-deck prompt

Shown for a deck with no cards and a blank `// Deck:` name or `// Format:`.

| Key | Action |
|-----|--------|
| type | Fill in the deck name / format |
| `Enter` | Next question / done |
| `Tab` | On the format: complete, cycling through the matches |
| `Up` / `Down` | Switch question |
| `Esc` | Skip (both lines stay editable with `i`) |

### Settings (`:config`)

| Key | Action |
|-----|--------|
| shared navigation | Move between settings |
| `h` / `l`, `Space` / `Enter` | Cycle the value back / forward |
| `s` | Save and close |
| `q` / `Esc` / `Ctrl-C` | Close; asks once more when there are unsaved changes |
| `?` | This screen's help topic |

### Help (`F1`, `:help`, `g?` panel)

Shared navigation. `q`, `Esc`, or `?` closes.

### History overlay (`gh`, `:history`)

A floating lazygit-style window with five panels: Working copy,
Branches, Snapshots, Diff, Stats.

| Key | Action |
|-----|--------|
| `1`-`5` / `Tab` / `Shift-Tab` | Jump to / cycle panels |
| shared navigation | Move the selection, or scroll the Diff and Stats panels |
| `Enter` | Open the item: switch to the branch, or jump to the Diff panel |
| `c` | Commit the working copy (prompts for a message) |
| `b` | Create a branch at the current tip |
| `B` / `D` | Switch to / delete the selected branch (Branches panel only) |
| `m` / `r` | Merge / rebase onto the selected branch (Branches panel only) |
| `t` / `T` | Tag / untag the selected snapshot (Snapshots panel only) |
| `R` | Restore the selected snapshot into the editor, y/N (Snapshots panel only) |
| `p` | Cherry-pick the selected snapshot onto the tip (Snapshots panel only) |
| `d` | Show or hide unchanged cards in the diff |
| `q` / `Esc` / `gh` | Close (`Esc` first cancels an open prompt) |
| `?` | This screen's help topic |

### Merge conflicts

| Key | Action |
|-----|--------|
| shared navigation | Move between conflicts |
| `o` / `t` | Take ours / theirs (auto-advances) |
| `c` | Custom quantity (`0` omits the card) |
| `u` | Unresolve |
| `Enter` | Confirm; every conflict must be resolved |
| `q` / `Esc` | Abort: nothing is committed |
| `?` | This screen's help topic |

## Remapping

`:map key action` remaps a key for the session (normal mode); `:unmap key`
removes a mapping. The key is a single key (`s`, `ctrl_s`), and, as in
vim, a mapping applies only where a command starts: mapping `s` leaves
`zs` and `"s` alone. Persistent maps live under `[keybindings]` in
`~/.config/vimtg/config.toml`, per mode (`normal`, `insert`, `visual`,
`command`). `;`, `,`, and `Ctrl-S` are unbound and free to map.

A mapping rewrites its key everywhere you type it, including as the
second key of a sequence. Mapping `s`, for example, also changes `zs`
and the mark, register, and macro names `ms`, `'s`, `"s`, `qs`, and
`@s`. Every letter is a mark, register, and macro name, so mapping any
letter has the same effect.

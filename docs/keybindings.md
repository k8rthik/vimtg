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
3. **One help vocabulary.** `?` opens help for the current screen and
   `F1` opens the full help, on every screen.
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
| `/` | Find a card (`:find` shorthand) |
| `Esc` | Back to normal mode; cancels a pending key sequence |
| `?` | Toggle the quick-reference panel |
| `F1` | Full-screen help |

### Navigation

| Key | Action |
|-----|--------|
| `j` / `k` | Down / up, skipping blank lines |
| `gg` / `G` | First / last line; `{n}G` goes to line `n` (`1G` is line 1) |
| `w` / `b` | Next / previous card entry |
| `{` / `}` | Previous / next section |
| `[[` / `]]` | Previous / next section or plan header |
| `[v` / `]v` | Previous / next sideboard plan (activates it) |
| `Ctrl-D` / `Ctrl-U` | Half page down / up |
| `0` / `$`, `h` / `l` | Line start / end (there is no horizontal cursor; nothing renders a column) |
| mouse wheel | Scroll three lines per notch, vim-style: the window moves and the cursor is dragged only when it would leave the screen |

Any motion takes a count: `10j`, `3w`.

### Editing

| Key | Action |
|-----|--------|
| `dd` / `yy` / `cc` | Delete / yank / change the card line (`cc` deletes, then opens card search) |
| `d` `y` `c` + motion | Operators compose with a motion: `dw` deletes a card entry, `d}` to the next section, `y5G` through line 5. Counts multiply: `2d3j` |
| `x` | Delete the card under the cursor (into the register); card lines only |
| `p` / `P` | Paste below / above; `3p` pastes three copies |
| `+` / `-` | Increment / decrement quantity; `-` at 0 deletes the line. Both keep zone prefixes, plan signs, `@category`, `#tags`, and comments |
| `.` | Repeat the last change (a count overrides the recorded one) |
| `u` / `Ctrl-R` | Undo / redo |

### Zones (`z` prefix)

| Key | Action |
|-----|--------|
| `zs` / `zm` / `zd` | Move the card to the **s**ideboard / **m**aybeboard / main **d**eck |
| `zc` / `zp` | Move the card to the **c**ommand zone (`CMD:`) / com**p**anion slot (`CMP:`) |
| `zo` / `zi` | Board the card **o**ut of / **i**nto the active sideboard plan (see `:plan`) |

A bare zone key moves every copy; a count splits: `2zs` moves two. Moves
keep the card's category, tags, and comment, merge into an existing line
in the target zone, and match the zone's block or prefix style.

### Marks, macros, registers

| Key | Action |
|-----|--------|
| `m{a-z}` | Set a mark (all 26 letters are available) |
| `'{a-z}` | Jump to a mark. Marks shift through inserts, deletes, puts, and zone moves |
| `q{a-z}` / `q` | Start recording a macro / stop recording |
| `@{a-z}` / `@@` | Play a macro / replay the last one; `3@a` plays three times |
| `"{a-z}` | Use a named register for the next yank, delete, or put. `"A`-`"Z` append, `"0` is the yank register, `"1`-`"9` the delete history |

### Visual mode

| Key | Action |
|-----|--------|
| `d` / `y` / `c` | Delete / yank / change the selection |
| `o` | Jump to the other end of the selection |
| `gc` / `gC`, `ta` / `tr` / `tt` | Category and tag prompts apply to the whole selection |
| `Esc` | Exit visual mode |

Other keys act on the cursor line only.

### Categories (`g` prefix)

| Key | Action |
|-----|--------|
| `gc` | Set the card's category (or the visual range). The prompt ghost-completes from this deck, previously used names, and presets; `Tab` accepts. In a category-grouped deck the card moves under its new header |
| `gC` | Clear the category; in a category-grouped deck the card moves to `// Uncategorized` |
| `gl` | Toggle layout: group by card type / by category |

`gg` (top) and `gh` (history overlay) share the prefix.

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
| `Ss` | **S**witch focus between the editor and the pane |
| `Sc` | **C**lose the pane |

While a pane is focused it uses the shared navigation keys (`j`/`k`,
`gg`/`G`, `Home`/`End`, `Ctrl-D`/`Ctrl-U`, wheel). The EDHREC pane adds
`h`/`l` (or `Tab`/`Shift-Tab`) to switch tabs and `Enter` to add the
selected card. `Esc` returns to the editor; `:` and `S` sequences pass
through; any other key refocuses the editor and runs there.

### Version control

| Key | Action |
|-----|--------|
| `gh` | Toggle the history overlay (see below) |

### Prefix map

| Prefix | Namespace | Keys |
|--------|-----------|------|
| `g` | go | `gg` `gc` `gC` `gl` `gh` |
| `t` | tags | `ta` `tr` `tt` `tf` `tl` `tc` `tn` `tp` |
| `S` | splits | `Sv` `Sh` `Sr` `Sa` `Ss` `Sc` |
| `z` | zones | `zs` `zm` `zd` `zc` `zp` `zo` `zi` |
| `m` / `'` | marks | `m{a-z}` `'{a-z}` |
| `q` / `@` | macros | `q{a-z}` `q` `@{a-z}` `@@` |
| `"` | registers | `"{a-z}` `"0` `"1`-`"9` |
| `[` / `]` | jumps | `[[` `]]` `[v` `]v` |
| `d` `y` `c` | operators | wait for a motion |

A mistyped sequence is dropped silently and the which-key popup closes.

### Card search (insert mode)

| Key | Action |
|-----|--------|
| typing | Updates the query; results appear from two characters |
| `Tab` / `Ctrl-J` / `Ctrl-N` / `Down` | Next result |
| `Shift-Tab` / `Ctrl-K` / `Ctrl-P` / `Up` | Previous result |
| `Enter` | Confirm (a duplicate in the same zone bumps its quantity) |
| `Esc` | Cancel; the scratch line is removed and the cursor restored |

### Command mode

| Key | Action |
|-----|--------|
| `Tab` / `Shift-Tab` | Accept the completion and cycle forward / back |
| `Enter` | Execute |
| `Esc` | Cancel |

Completion is fuzzy: `:so` matches `sort`, `:st` matches `sort` and `stats`.

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
| `n` / `e` / `i` / `s` / `r` | New deck / open a file / import a file or URL / sync cards / recent decks |
| `1`-`5` | Open the nth recent deck |
| `?` / `F1` | Help overview (scrolls with the shared keys) |
| `q` | Quit vimtg. `Esc` does nothing on the menu; in a sub-mode it goes back |
| lists | Shared navigation, `Enter` open, `n` new deck, `q`/`Esc` back |
| import | Type or paste a path or URL, `Enter` import, `Esc` back |

### Settings (`:config`)

| Key | Action |
|-----|--------|
| shared navigation | Move between settings |
| `h` / `l`, `Space` / `Enter` | Cycle the value back / forward |
| `s` | Save and close |
| `q` / `Esc` / `Ctrl-C` | Close; asks once more when there are unsaved changes |
| `?` | This screen's help topic |

### Help (`F1`, `:help`, `?` panel)

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
removes a mapping. Persistent maps live under `[keybindings]` in
`~/.config/vimtg/config.toml`, per mode (`normal`, `insert`, `visual`,
`command`). Unbound keys such as `;`, `,`, `e`, `f`, `n`, `r`, `s`, or
`Ctrl-S` are free to map.

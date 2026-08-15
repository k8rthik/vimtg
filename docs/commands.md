# Ex commands

All commands are entered after `:` in normal mode. Most accept a vim-style
range prefix (`%` for the whole file, `5,10` for a line range, `.` for the
current line, `'a,'b` for marks).

## File

| Command | Description |
|---------|-------------|
| `:w [file]` | Save deck. Without an argument, writes back to the loaded file |
| `:q` | Quit. Errors if there are unsaved changes (E37) |
| `:q!` | Quit, discarding changes |
| `:wq` | Save and quit |
| `:e file` | Open `file`, replacing the current buffer |

## Editing

| Command | Description |
|---------|-------------|
| `:sort [field]` | Sort the current section. Fields: `name`, `cmc`, `type`, `color`, `qty`, `tag`. `:sort!` reverses |
| `:%sort name` | Sort the entire deck alphabetically |
| `:s/old/new/[flags]` | Substitute. Flags: `g` (all), `i` (case-insensitive) |
| `:%s/Bolt/Helix/g` | Substitute across the deck |
| `:g/pattern/cmd` | Run `cmd` on every line matching `pattern` |
| `:v/pattern/cmd` | Inverse: run on every line **not** matching |

Examples:

```
:g/Creature/d            delete every line matching "Creature"
:%s/Mountain/Plains/g    swap every Mountain for Plains
:1,20sort cmc            sort lines 1–20 by mana cost
```

## Search & navigation

| Command | Description |
|---------|-------------|
| `:find pattern` | Jump to the next card matching `pattern` (also bound to `/`) |
| `:search query` | Open the card database search overlay |

## Tags

| Command | Description |
|---------|-------------|
| `:tag name` | Tag the current line (or range) `#name` |
| `:untag name` | Remove `#name`. `:untag!` clears every tag in the range |
| `:tags` | List every tag in the deck with counts |
| `:filter expr` | Filter the view to cards matching the tag expression |
| `:retag /old/new/` | Rename a tag everywhere it appears |
| `:dtag name` | Delete every card tagged `#name` |

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
| `:export fmt [file]` | Write the deck as `arena`, `mtgo`, `moxfield`, `archidekt`, or `vimtg` |
| `:import file` | Replace the buffer with `file`, auto-detecting format |
| `:clipboard [fmt]` | Copy the deck to the system clipboard (default arena) via OSC52 |

## Version control

vimtg keeps a git-like commit graph per deck (lazygit-style history
screen, persistent branches, merges, and rebases). Branches and the
current branch survive across sessions.

| Command | Description |
|---------|-------------|
| `:history` (alias `:log`) | Open the history screen |
| `:commit "msg"` | Snapshot the current deck state |
| `:checkpoint name` | Commit the current state and tag it |
| `:branch` | List branches (`*` marks the current one) |
| `:branch name` | Create a new branch at the current tip |
| `:branch! name` | Switch to an existing branch (loads its tip) |
| `:merge branch` | Merge a branch (3-way; fast-forwards when possible) |
| `:merge path.deck` | Merge another deck file's cards (empty merge base) |
| `:rebase branch` | Replay this branch's commits onto another branch tip |

Merging and rebasing require a committed working state (`:commit` first).
When both branches changed the same card differently, an interactive
resolution screen opens: pick ours, theirs, or a custom quantity per
card. Merge commits record both parents; the log shows the first-parent
history with a `⇄ merge` marker. Rebase replays commits with a
replayed-change-wins policy and leaves the original snapshots recoverable
by id. Note that merge and rebase results are normalized on write
(sections regrouped, free comments dropped), like cherry-pick.

## Analytics

| Command | Description |
|---------|-------------|
| `:stats` | Toggle the mana-curve / type / color / price panel |
| `:validate` | Check 60-card minimum, 4-of rule, sideboard limits |

## Configuration

| Command | Description |
|---------|-------------|
| `:config` | Open the settings screen |
| `:set key=value` | Set an editor option for this session |

## Help

| Command | Description |
|---------|-------------|
| `:help` | Open full-screen help overview (also `F1`) |
| `:help cmd` | Open help for a specific command |

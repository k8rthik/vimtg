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
| `:sort [field]` | Sort the current section. Fields: `name`, `cmc`, `type`, `color`, `qty`, `tag`, `category`, `power`, `toughness`, `rarity`, `price`. No field uses the `sort_order` setting (default `cmc`). `:sort!` reverses |
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
recommendations for the deck's commander. `Ss` switches focus into the
pane (`j`/`k` scroll or select, `h`/`l` switch tabs, `Esc` returns).

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
| `:validate` | Check format legality: deck size, copy limits, sideboard rules, commander rules (exact 100 cards, singleton, no sideboard, legendary commander, ≤2 partners, color identity), and sideboard-plan consistency |
| `:analytics` | Live analytics pane: curve, counts per type/zone/category, mana base, draw odds (alias `:ana`, key `Sa`); with a plan active it shows the post-board deck |

## Sideboard plans

A plan is a `VS: <matchup>` block at the end of the deck listing
`-N Card` (out of the mainboard) and `+N Card` (in from the sideboard)
lines — see [deck-format.md](./deck-format.md#sideboard-plans). One plan
is *active* at a time: `mo`/`mi` write into it, deck cards show their
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
| `:set key=value` | Set an editor option for this session |

Card data auto-syncs in the background when the local database is
missing or older than a week (`:set noautosync` turns this off; the
`vimtg sync` CLI command always works manually).

## Help

| Command | Description |
|---------|-------------|
| `:help` | Open full-screen help overview (also `F1`) |
| `:help cmd` | Open help for a specific command |

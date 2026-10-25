# Version history

Every saved deck has a linear history in vimtg's database: `:w` takes a snapshot, `:commit <message>` names one, `:checkpoint <name>` names and tags one, and the floating history overlay (`gh`) shows snapshots, diffs, and stats deltas, with tag and restore.

## Sub-features

- `vcs-commit` names a snapshot with `:commit <message>`; nothing new says `Nothing to commit`.
- `vcs-overlay` opens and closes the history overlay with `gh` (`:history`, `:log`).
- `vcs-checkpoint` commits and tags in one step (`:checkpoint <name>`); the Snapshots panel shows the tag in parentheses.
- `vcs-gone` the git-style `:branch`, `:merge` and `:rebase` are not commands (`E492`).
- `vcs-unsaved` refuses history on a deck never written (`E32: No file name`).

## How to get to it (user POV)

- `gh` in normal mode toggles the overlay; `q`, `Esc`, or `gh` close it.
- Ex commands `:commit`, `:checkpoint`, `:history` (`:log`, `:hist`).

## Driving it with vv

Preconditions:

- `$V tui start burn.deck` and `$V wait "F1 help" 20` succeeded on a fresh sandbox (empty history).

- **Save, then commit.** `$V find "Lava Spike"; $V type +; $V type ":w"; $V keys Enter; $V wait "Written"`, then `$V type ":commit more spikes"; $V keys Enter; $V wait "Snapshot: more spikes"`.
- **Nothing new.** `$V type ":commit again"; $V keys Enter; $V wait "Nothing to commit"`. The message names snapshot `more spikes`.
- **Overlay.** `$V type gh; $V wait "History"; $V shot vcs-overlay`. A floating window titled `History — Burn` lists `more spikes` in its Snapshots panel, with panels `1 Working copy`, `2 Snapshots`, `3 Diff`, `4 Stats` and no Branches panel. `$V type q` closes it and the deck is back with the cursor where it was.
- **Checkpoint.** `$V type ":checkpoint v1"; $V keys Enter; $V wait "Checkpoint: v1"`; in the overlay the snapshot line carries `(v1)`.
- **Gone.** `$V type ":branch"; $V keys Enter; $V wait "E492: Not an editor command: branch"`.
- **Unsaved deck.** `$V type ":enew!"; $V keys Enter`, finish or `Esc` the wizard, then `$V type ":commit x"; $V keys Enter`. The message is `E32: No file name`.

## Gotchas

- History is stored per deck path in the sandbox's database, so a fresh sandbox always starts empty. Reusing a run carries old snapshots.
- `:w` snapshots as `auto: save`. A `:commit` right after it renames that snapshot rather than adding a second one: assert the description, not the count.
- In the overlay `?` opens its help (another floating window over it); in the editor `?` is search.

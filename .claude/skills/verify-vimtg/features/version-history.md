# Version history

Every saved deck has a git-like history in vimtg's database: `:w` takes a snapshot, `:commit <message>` names one, and the floating history overlay (`gh`) shows snapshots, diffs, branches, and stats deltas, with restore, branch, merge, and cherry-pick.

## Sub-features

- `vcs-commit` names a snapshot with `:commit <message>`; nothing new says `Nothing to commit`.
- `vcs-overlay` opens and closes the history overlay with `gh` (`:history`, `:log`).
- `vcs-branch` creates and switches branches (`:branch <name>`, `:branch`).
- `vcs-unsaved` refuses history on a deck never written (`E32: No file name`).

## How to get to it (user POV)

- `gh` in normal mode toggles the overlay; `q`, `Esc`, or `gh` close it.
- Ex commands `:commit`, `:checkpoint`, `:branch`, `:merge`, `:rebase`, `:history`.

## Driving it with vv

Preconditions:

- `$V tui start burn.deck` and `$V wait "F1 help" 20` succeeded on a fresh sandbox (empty history).

- **Save, then commit.** `$V find "Lava Spike"; $V type +; $V type ":w"; $V keys Enter; $V wait "Written"`, then `$V type ":commit more spikes"; $V keys Enter; $V wait "Snapshot: more spikes"`.
- **Nothing new.** `$V type ":commit again"; $V keys Enter; $V wait "Nothing to commit"`. The message names snapshot `more spikes`.
- **Overlay.** `$V type gh; $V wait "History"; $V shot vcs-overlay`. A floating window titled `History — Burn` lists `more spikes` in its Snapshots panel. `$V type q` closes it and the deck is back with the cursor where it was.
- **Branch.** `$V type ":branch sideboard-test"; $V keys Enter`, then `$V type ":branch"; $V keys Enter` lists both branches with the current one marked.
- **Unsaved deck.** `$V type ":enew!"; $V keys Enter`, finish or `Esc` the wizard, then `$V type ":commit x"; $V keys Enter`. The message is `E32: No file name`.

## Gotchas

- History is stored per deck path in the sandbox's database, so a fresh sandbox always starts empty. Reusing a run carries old snapshots.
- `:w` snapshots as `auto: save`. A `:commit` right after it renames that snapshot rather than adding a second one: assert the description, not the count.
- In the overlay `?` opens its help (another floating window over it); in the editor `?` is search.

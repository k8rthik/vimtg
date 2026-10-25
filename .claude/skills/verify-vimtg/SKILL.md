---
name: verify-vimtg
description: Drive the real vimtg TUI (and its CLI) in an isolated, offline sandbox to prove a change works the way a user would see it. Use after changing editor keys, ex commands, screens, panes, the greeter, import/export, history, or the tutor, and before calling such work done. Runs the actual `vimtg` binary in a per-run tmux server, sends real keystrokes, and saves screen captures as evidence.
---

# Verify vimtg

vimtg is a vim-style terminal editor for Magic: The Gathering decklists (Python, Textual). Users touch two surfaces: the **TUI** (`vimtg`, `vimtg deck.deck`, `vimtg tutor`) and the **CLI** subcommands (`vimtg validate|info|diff|missing|convert|search|hand|guide|sync|new`). This skill drives both through `scripts/vv`, a bash helper that owns one sandbox and one tmux server per run.

Unit and pilot tests live in `tests/` (`uv run pytest`). They are not proof that a user can do something. This skill is: real binary, real terminal, real keystrokes, captured screens and files.

All commands run from the repository root. `V=.claude/skills/verify-vimtg/scripts/vv` keeps them short.

## Launch

```bash
V=.claude/skills/verify-vimtg/scripts/vv
uv sync --extra dev                 # once per checkout
$V sandbox                          # or: $V sandbox <run-id>
$V tui start burn.deck              # or: $V tui start   (greeter)   /   $V tui start tutor
$V wait "F1 help" 20                # deck view ready (hint bar drawn)
```

- `sandbox` creates `.verify/runs/<id>/` with `sandbox/` (XDG data, config, cache, state, and `decks/`) and `evidence/`, points `.verify/current` at it, and loads 84 cards offline: the README demo set (`docs/demo/cards.json`, Commander goblins) plus the tutor bundle (`src/vimtg/tutor/cards.jsonl.gz`, modern burn with real legalities). It also loads a small oracle-tag set (`fixtures/oracle_tags.jsonl`: real Scryfall tag records such as `ramp` > `mana-producer` > `mana-rock` and `tutor` > `tutor-creature` > `tutor-creature-goblin`, tagging the demo cards), so `otag:` searches work. It runs `vimtg sync` against that cache, so nothing is downloaded. `00-sync.txt` in evidence is the load log. `VV_TAGS=0 $V sandbox <id>` leaves the tags out: the sync's tag download is sent to a dead loopback proxy, so `00-sync.txt` shows the `Oracle tags skipped:` fallback and `otag:` searches show the `oracle tags not synced` note.
- Seed decks in `sandbox/decks/` (the TUI's working directory): `burn.deck` (modern, typed sections, sideboard, a `VS: Tron` plan; from `fixtures/burn.deck`) and `krenko.deck` (100-card Commander). `collection.csv` (ManaBox headers, from `fixtures/collection.csv`) owns part of `burn.deck`: 3 Lightning Bolt over two printings, 4 Goblin Guide, 2 Monastery Swiftspear, 4 Lava Spike, 14 Mountain, 4 Arid Mesa, 1 Rest in Peace.
- Ready signals: the deck view shows the hint bar `F1 help`; the greeter shows `Tutorial` in its menu; the tutor shows `W E L C O M E`.
- `VIMTG_NO_AUTOSYNC=1` and `VIMTG_NO_EDHREC=1` are set, so the app never touches the network. EDHREC shows a "lookups disabled" status by design.
- A short-lived CLI needs no launch: `$V cli <args>` runs it in the sandbox.

## Doctor

```bash
$V doctor
```

Read-only. Prints the run dir, `vimtg --version`, the checkout's HEAD, the sandbox card count and `(card, tag)` row count, whether every XDG dir is inside the run, and whether the TUI is running or exited (with its status). Ends `doctor: OK` or `doctor: FAIL` (exit 1). Run it first whenever anything looks off. A card count of 0 means the load failed: read `evidence/00-sync.txt`.

## Drive

| Need | Command |
|---|---|
| Type text literally | `$V type ":w copy.deck"` |
| Jump to a card | `$V find "Lightning Bolt"` (types `/Lightning Bolt` Enter, waits for the jump, exit 1 on `Pattern not found`) |
| Named keys (tmux names) | `$V keys Enter`, `Escape`, `C-a`, `C-x`, `C-o`, `C-w`, `C-r`, `Space`, `Tab`, `BSpace`, `F1`, `Up` |
| Wait for the app to react | `$V wait "Written: burn.deck"` (exit 1 and screen dump on timeout) |
| Capture evidence | `$V shot <label>` saves `evidence/NN-<label>.txt` and prints it |
| App state | `$V status` prints `running` or `exited <code>` |
| CLI | `$V cli validate burn.deck` saves `NN-cli.cmd/.out/.err/.exit` |
| A shell in the sandbox | `eval "$($V env)"` then any command |

Stable handles to wait on and assert against:

- Command-line messages are literal: `Written: <file>`, `"copy.deck" written`, `Moved 2x <card> to sideboard (2 remain)`, `Added 4x <card>`, `Filter cleared`, `Type :q and press Enter to exit vimtg`, `E37: No write since last change (add ! to override)`, `E492: Not an editor command: <cmd>`, `search hit BOTTOM, continuing at TOP`.
- Card lines render as `<row>  <qty>   <name>  <cost>  <type>`; the gutter shows `✗` (error) or `!` (warning) before the row number.
- The cursor card's rules text shows on the next line after `│`.
- Overlays draw a rounded border with their title (`History — <deck>`, `vimtg Help`, `Messages`, `Sample hand`, `Settings`) and their close keys in the bottom border.
- Panes: opening analytics prints `Analytics pane open` on the command line.

Typical step: act, wait for the message, shot, then check the side effect.

```bash
$V find "Lightning Bolt"
$V keys C-a; $V shot ctrl-a                       # shows "5   Lightning Bolt" and a ✗
$V type ":w"; $V keys Enter; $V wait "Written: burn.deck"; $V shot saved
grep -n "Lightning Bolt" .verify/current/sandbox/decks/burn.deck   # 5 Lightning Bolt
```

The feature map in [`features/`](features/README.md) has the recipes per feature. Read its README first.

## Evidence

- Everything goes to `.verify/runs/<id>/evidence/` (gitignored). Numbered files keep the order of actions: `NN-<label>.txt` screens and `NN-cli.*` CLI runs.
- A proof captures the action and the result: a shot before and after the keys, the message line, and the side effect on disk (`sandbox/decks/*.deck`, `cat` it or `grep` it, or a second view such as `$V cli info burn.deck` or reopening the deck).
- Drive the real user path: keys and ex commands as a user types them. Never call internal functions or edit `sandbox/` files to fake a state the user path should reach.
- The sandbox is offline by construction (no autosync, no EDHREC). A feature that needs the network (`vimtg sync` from Scryfall, deck URL import, EDHREC data) cannot be proven here: report it as not verified, with the reason.
- Quote the evidence paths in your report.

## Cleanup

```bash
$V cleanup
```

Kills only this run's tmux server (`tmux -L vimtg-verify-<id>`), deletes `sandbox/`, and removes the `.verify/current` link. `evidence/` stays. Run it after every attempt, failed ones too. Never `pkill vimtg` or kill tmux by name: the user may be running their own vimtg.

## Isolation

Each run has its own XDG dirs, decks, and tmux socket, so runs can go side by side: give each a run id (`$V sandbox a`, `$V sandbox b`) and select one per command with `VV_RUN=.verify/runs/a $V ...`. The user's real card database, decks, history, and config are never read or written. `doctor` fails if the XDG dirs escape the run.

# Zones and sideboard plans

A card lives in one zone: main deck, sideboard (`SB:`), maybeboard (`MB:`), command zone (`CMD:`), or companion (`CMP:`). The `z` keys move cards between zones, a count splits copies off, and `VS:` blocks describe sideboard plans against a matchup. The deck's `// Format:` drives live legality signs in the gutter and `:validate`.

## Sub-features

- `zone-move` moves a card with `zs`/`zm`/`zd`/`zc`/`zp`; `2zs` moves two copies.
- `zone-plan` activates a plan with `:plan <name>`; `zo`/`zi` board the cursor card out/in.
- `zone-legal` shows `✗`/`!` gutter signs and `:validate` lists every problem.

## How to get to it (user POV)

- Normal-mode `z` keys on a card line (pause after `z` to see the which-key menu).
- `:plan`, `:plans`, `[v` / `]v` for plans; `:validate` for legality.
- `vimtg validate <deck>` and `vimtg guide <deck>` from the shell.

## Driving it with vv

Preconditions:

- `$V tui start burn.deck` and `$V wait "F1 help" 20` succeeded on a fresh fixture.

- **Split copies to the sideboard.** `$V find "Skewer the Critics"; $V type 2zs; $V wait "Moved 2x Skewer the Critics to sideboard (2 remain)"`. The cursor is on the new `SB: 2   Skewer the Critics` line.
- **Bring them back.** `$V type zd; $V wait "Moved 2x Skewer the Critics to main deck"`. The main-deck line reads `4   Skewer the Critics` again and no `SB:` Skewer line remains.
- **Activate a plan.** `$V type ":plan Tron"; $V keys Enter; $V wait "vs Tron"`.
- **Board a card out.** `$V find "Monastery Swiftspear"; $V type zo; $V wait "vs Tron: -4 Monastery Swiftspear"`. The `VS: Tron` block gains `-4 Monastery Swiftspear`.
- **Legality.** `$V keys C-a` on any 4-of: `✗` appears in its gutter and the status bar names the rule. `$V type ":validate"; $V keys Enter` lists the problems (in the floating `Messages`-style pager when it is longer than one line; `q` closes it).
- **Second view.** `$V type ":w"; $V keys Enter; $V wait "Written"`, then `$V cli guide burn.deck` prints `vs Tron` with the boarded lines, and `$V cli validate burn.deck` prints the same errors with exit code `1`.

## Gotchas

- `zc` on a card that cannot be a commander still moves it, with a warning in the message: assert the message, not just the move.
- A zone move carries the cursor to the card's new line, which may be far away.
- Plan lines (`+2 Name`, `-4 Name`) live indented under `VS:`; `zo`/`zi` act only when a plan is active, otherwise they say so.
- `krenko.deck` is Commander: `2zs` there is refused or flagged differently (Commander has no sideboard). Use `burn.deck` for zone recipes.

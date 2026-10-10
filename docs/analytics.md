# Analytics methodology

How `:stats`, the `:analytics` pane (`Sa`) and the bracket note in
`vimtg validate` compute their numbers. Everything here is computed from
the synced Scryfall data; nothing is fetched live.

## Which cards count

- **Played cards** are the mainboard plus the command zone. The
  commander is cast like any other spell, so it counts toward the
  totals, the curve, the colour pips and the mana-base requirements.
  Draw odds still use the mainboard only, because the commander is not
  in the library. The sideboard, companion and maybeboard only show up
  in the zone counts (the sideboard is also in the `:stats` total).
- **Lands are classified by front face.** A modal double-faced spell
  with a land back (`Valakut Awakening // Valakut Stoneforge`,
  `Instant // Land`) counts as a spell: it is on the curve and not in
  `MANA BASE (N lands)`. Pathways (`Land // Land`) and other
  land-fronted cards are lands.

## Colour pips

Every coloured symbol in the mana cost is a pip of its colour. A hybrid
symbol is a pip of **each** of its colours (`{R/G}` counts once for red
and once for green; `{2/W}` counts for white). A Phyrexian symbol counts
for its colour (`{B/P}` is a black pip), because paying life does not
remove the need for a source if you want to pay mana. Generic, `{X}`,
`{C}` and snow symbols are not coloured pips.

## Mana sources

A land counts as a source for a colour when it can **produce** it or
**fetch** a land that produces it:

1. **Produced mana**: Scryfall's `produced_mana`. Command Tower and City
   of Brass count for every colour (Command Tower only makes your
   commander's colours, but you will not have pips outside them).
2. **Fetch lands** (heuristic, read from the oracle text):
   - `Search your library for a Mountain or Plains card` counts for the
     colours of the basic land types it names (Arid Mesa: red and white).
   - `Search your library for a basic land card` (Evolving Wilds, Fabled
     Passage, Prismatic Vista) counts for the colours of the basic lands
     actually in the deck. With no basics, it counts for nothing.
   - Anything else counts for nothing. This errs on the side of
     reporting too few sources rather than too many.
3. **Older card databases**: when a card has no stored `produced_mana`
   (a database synced before vimtg stored it), its basic land types
   (`Land — Mountain Plains`) and its colour identity are used instead.
   Run `vimtg sync --force` to get the exact data.

The requirement per colour is the deck's most demanding card under Frank
Karsten's source table (pips vs. turn = mana value), scaled to the
mainboard size. It is shown as `sources/needed`, with `✓` or
`✗ need N more`.

## Suggested land count

The pane shows `suggested ~N lands (Karsten estimate)` under the mana
base. It uses Frank Karsten's regression fits on the average mana value
of the played nonland cards:

- decks of 80+ played cards (Commander): `31.42 + 3.13 × average MV`;
- smaller decks: `19.59 + 1.90 × average MV`, scaled from 60 cards to
  the actual size (a 40-card Limited deck lands near 17).

Karsten also subtracts about 0.28 lands per cheap card-draw or ramp
spell. vimtg cannot tell which cards those are, so the hint leaves that
term out and runs high for decks with a lot of ramp. No hint is shown
until there is at least one resolved nonland card.

## Prices

`:stats` totals the price source set by `:set price_source=...` (`usd`
by default) and names it, for example `$123.45 (usd)` or
`€98.10 (eur)`.

## Commander brackets

For Commander decks (`// Format: commander`, or no format and a card in
the command zone) the pane has a **COMMANDER BRACKET** section, and
`vimtg validate` prints an `info:` line, listing the deck's Game
Changers and an estimated bracket:

| Game Changers | Estimated bracket |
|---------------|-------------------|
| 0             | 1-2               |
| 1-3           | 3                 |
| 4 or more     | 4+                |

This follows the official bracket definitions: Brackets 1 and 2 allow no
Game Changers, Bracket 3 allows up to three, and Brackets 4 and 5 have
no limit. Sources:

- Commander format page, including the current bracket definitions and
  Game Changers list: <https://magic.wizards.com/en/formats/commander>
- Latest bracket update used (February 9, 2026):
  <https://magic.wizards.com/en/news/announcements/commander-brackets-beta-update-february-9-2026>

**The estimate is a heuristic.** It only counts Game Changers, which
sets the lowest bracket a deck can be in. Mass land denial, chained
extra turns, two-card combos and, above all, the deck's intent can
put it in a higher bracket, and vimtg does not check any of those. The
Game Changer flag comes from Scryfall (`game_changer`) as of your last
`vimtg sync`. The note is informational: it is never an error, and
`vimtg validate --strict` does not fail on it.

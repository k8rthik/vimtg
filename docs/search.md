# Card search syntax

The `o`/`O` search overlay and `vimtg search` use the same
Scryfall-style parser. Every search runs against your local card database, so
it works offline.

```
t:creature c:g mv<=3                  green creatures with mana value 3 or less
-t:land (c:boros or id:esper) r>=rare  non-land rares+ that are Boros or in Esper
o:"draw a card" f:modern usd<1        cheap modern-legal card draw
!"Lightning Bolt"                     exactly that card
is:mdfc t:land                        modal DFCs with a land face
o:/deals \d damage/                   regex on rules text
otag:ramp c:g mv<=3                   cheap green ramp, by Scryfall's oracle tags
```

## Combining terms

| Syntax | Meaning |
|--------|---------|
| `a b` | both (`and` may be written but is optional) |
| `a or b` | either; `or` binds looser than and: `c:r t:elf or t:goblin` is `(c:r t:elf) or t:goblin` |
| `( … )` | grouping |
| `-term`, `-( … )` | negation |
| `"quoted phrase"` | words in that order; also quotes a value: `o:"draw a card"` |

## Terms

| Term | Matches |
|------|---------|
| bare word, `"phrase"` | word-prefix match on the card name, any face (`light` finds Lightning Bolt, `stomp` finds Bonecrusher Giant). Accents and ligatures fold (`aether` = `Æther`) |
| `!name`, `!"full name"` | the exact full name or one face, case- and punctuation-insensitive |
| `/regex/` | regex on the name |
| `name:text` | substring of the name |
| `t:` `type:` | type line substring, any face |
| `o:` `oracle:` `fo:` | rules text substring, any face (back faces of transform and modal DFCs included). Accepts `/regex/` |
| `kw:` `keyword:` | a whole keyword (`kw:flying`); also its "with" form, so `kw:partner` finds Partner and Partner with |
| `m:` `mana:` | mana cost contains symbols: `m:rr` or `m:{R}{R}`. Split cards store both halves (`{3}{U} // {4}{W}{W}`), so `m:ww` finds Commit // Memory |
| `produces:` | mana the card can produce: `produces:g`, `produces:ur` (at least those), `produces=c` (exactly colourless), `produces<=ub`; colour words and guilds work too |
| `c:` `color:` `colour:` | colours (see below) |
| `id:` `ci:` `identity:` | colour identity (see below) |
| `mv` `cmc` `manavalue` | mana value |
| `pow` `power`, `tou` `toughness` | power / toughness of **any face** (Delver of Secrets matches `pow>=3` by its back face; cards without one never match; `*` counts as 0). Compare two stats with `pow>tou`, `tou<=mv`, `pow=cmc` |
| `r:` `rarity:` | `common`, `uncommon`, `rare`, `mythic`, `special`, `bonus` (or `c`/`u`/`r`/`m`); ordered, so `r>=rare` works |
| `s:` `set:` `e:` `edition:` | set code of the stored printing |
| `f:` `format:` `legal:` | playable in the format: legal **or restricted** |
| `banned:`, `restricted:` | banned / restricted in the format |
| `usd` `eur` `tix` | price comparisons; cards without that price never match |
| `is:` / `not:` | `commander`, `dfc`, `mdfc`, `transform` (`tdfc`), `split`, `adventure`, `flip`, `meld`, `gamechanger` (`gc`), `permanent` (front face is an artifact, creature, enchantment, land, planeswalker or battle), `spell` (front face is not a land), `hybrid` (a hybrid symbol in the cost, `{2/W}` included), `phyrexian` (a Phyrexian symbol in the cost) |
| `otag:` `oracletag:` `function:` | a Scryfall oracle tag (see below): `otag:ramp`, `otag:removal`, `otag:tutor`, `otag:card-advantage`. A card matches the tag or any tag under it; aliases work (`otag:acceleration` is `ramp`); a tag nobody has matches nothing |
| `order:` `direction:` | sort results instead of ranking by name: `order:` `name`, `cmc` (`mv`), `power`, `toughness`, `rarity`, `usd`, `eur`, `tix`, `set`; `direction:asc` or `desc`. Cards without the value sort last |

Typographic quotes and apostrophes fold to plain ones, so a pasted
`o:“can’t be countered”` finds "can't be countered".

Numeric keys, colours and `produces:` take any comparison operator: `:` `=` `!=` `<` `<=`
`>` `>=` (`:` means `=` for numbers and rarity). Text keys take `:` only.

Formats are Scryfall's legality keys (`standard`, `pioneer`, `modern`,
`legacy`, `vintage`, `pauper`, `commander`, `brawl`, `standardbrawl`,
`oathbreaker`, `paupercommander`, `duel`, `premodern`, `penny`, `historic`,
`timeless`, `explorer`, `alchemy`, `gladiator`, …). Names are
case-insensitive, ignore spaces and hyphens, and accept these aliases:
`edh`/`cedh` (commander), `pdh` (paupercommander), `historicbrawl`
(brawl), `duelcommander` (duel), `pennydreadful` (penny). Deck
validation reads `// Format:` with the same table, so `// Format: EDH`
and `f:edh` mean the same format.

Formats with deck-construction rules in validation, besides the
paper formats: Explorer, Alchemy, Historic and Timeless (60-card
minimum, up to 15 sideboard cards, 4 copies) and Gladiator (at least 100
cards, one copy of each card but basic lands, no sideboard, no
commander). Sources: the official format pages
<https://magic.wizards.com/en/formats/explorer>,
<https://magic.wizards.com/en/formats/alchemy>,
<https://magic.wizards.com/en/formats/historic>,
<https://magic.wizards.com/en/formats/timeless> and
<https://magic.wizards.com/en/formats/gladiator>. `future`, `oldschool`
and `predh` work in searches only.

`is:commander` follows the Commander rules: a legendary creature, Vehicle,
Spacecraft with P/T or Background, or a card whose text says it can be your
commander.

## Oracle tags

Scryfall's volunteers tag every card by what it does (the Tagger project,
`otag:` on scryfall.com). `vimtg sync` downloads the tag list (about 6 MB)
after the card data, so `otag:` works offline like every other term. Tags
form a tree: `otag:removal` finds cards tagged `removal-burn`,
`removal-artifact`, `sweeper` and every other tag under `removal`. Spaces in
a quoted tag become hyphens, so `otag:"mana rock"` is `otag:mana-rock`.

```
otag:ramp t:artifact mv<=2            Sol Ring and its friends
otag:tutor id<=bg f:commander         tutors playable under a Golgari commander
-otag:removal t:instant c:r           red instants that are not removal
```

On a database synced before vimtg had oracle tags, an `otag:` search
matches nothing and says `oracle tags not synced` until the next `vimtg sync`
(`:sync` in the editor).

## Colours

Colours are letters (`wubrg`, `c` for colourless, `m` for multicolour), names
(`white` … `green`, `colorless`, `multicolor`), guilds (`boros`, `azorius`, …),
shards (`esper`, `jund`, …), wedges (`mardu`, `temur`, …), or a count
(`c>=2`).

| Query | Meaning |
|-------|---------|
| `c:rg` | at least red and green (Scryfall's `c:`) |
| `c=rg` | exactly red-green |
| `c<=rg` | within red-green (includes colourless) |
| `c<rg` / `c>rg` | strict subset / strict superset |
| `c!=rg` | anything but exactly red-green |
| `id:esper` | identity **within** Esper: playable under an Esper commander (Scryfall's `id:`) |
| `id>=wb`, `id=simic` | identity at least / exactly |
| `c:c`, `id:c` | colourless |

## Results and errors

Results are ranked by how well the bare name words match, then sorted by name,
and capped at `search_limit` (`vimtg search -n N` on the command line). In the
editor, cards not playable in the deck's declared format are filtered out before
the limit is applied.

An unknown key (`foo:bar`), colour, rarity, format, `is:` value, sort
order, malformed number, or invalid regex is reported by name in the overlay (or as a CLI error)
instead of being ignored. `year:` and `date:` are not supported, because
vimtg stores one printing per card, and say so. Unfinished syntax at the end of what you are typing —
an open quote or parenthesis, a trailing `-` or `or`, an empty `t:` — is
tolerated so as-you-type search keeps working.

On the command line, separate shell words form one query. Put `--` before a
query that starts with `-`: `vimtg search -- -t:land c:boros`.

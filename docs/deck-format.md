# `.deck` file format

vimtg decks are plain text. The format is line-oriented, git-friendly, and
readable without any tooling. It is **not** strictly defined by a grammar —
vimtg's parser is intentionally permissive. The rules below describe what
vimtg writes; it accepts more than it produces.

## Line types

Each line is one of:

| Kind | Pattern | Example |
|------|---------|---------|
| Metadata | `// key: value` | `// Deck: Burn` |
| Deck block header | `DCK:` | `DCK:` (cards beneath are mainboard) |
| Section header | `// header text` | `// Creatures` |
| Category header | `// @name` | `// @ramp` |
| Card entry | `[N] CardName [@category] [#tag …] [// comment]` | `4 Lightning Bolt  @removal  #burn  // core` |
| Sideboard entry | `SB: [N] CardName [#tag …] [// comment]` | `SB: 2 Rest in Peace` |
| Maybeboard entry | `MB: [N] CardName …` | `MB: 1 Opt` |
| Commander entry | `CMD: [N] CardName …` | `CMD: 1 Atraxa, Praetors' Voice` |
| Companion entry | `CMP: [N] CardName …` | `CMP: 1 Lurrus of the Dream-Den` |
| Blank | (empty) | |

## Metadata keys

Recognized at the top of the file:

| Key | Meaning |
|-----|---------|
| `Deck` | Deck name (used in greeter, history) |
| `Format` | Format name (`modern`, `legacy`, `commander`, …). Editing the value with `i` ghost-completes the formats with legality rules (Tab accepts); an unrecognized format gets a gutter warning on the line — the deck still works, but legality checking is off |
| `Author` | Optional |
| `Source` | Optional (URL or provenance note) |
| `Tags` | Deck-level tags, comma-separated |

Values may be empty (`// Format:`) — new decks are scaffolded with empty
`// Deck:`, `// Format:`, and `// Tags:` lines, and any deck missing them
gets them added (in the buffer only) on open. Press `i` on a metadata line
to edit just the value; the `// Key:` prefix is locked.

The `Format` value drives live legality checking: illegal cards get a
gutter sign (`✗` error, `!` warning) and the reason appears in the status
bar when the cursor is on the line. `:validate` prints the full list.

Unknown keys are preserved on save.

## Sections

A line matching a known header word (`// Creatures`, `// Lands`, …) or the
category form `// @name` is a section header. Sections are purely visual —
they affect rendering and the `{` / `}` motions but have no semantic
meaning. Any other `// text` line is a freeform comment.

```
// Creatures
4 Goblin Guide
4 Monastery Swiftspear

// Spells
4 Lightning Bolt
```

## Categories

`N CardName [@category]`

A card may carry at most one `@category` token — a user-defined purpose
label (`@ramp`, `@draw`, `@wincon`) that drives the category layout.
`:layout category` regroups the mainboard under `// @name` headers;
`:layout type` regroups by card type while each card keeps its token, so
toggling is lossless. Set with `gc` / `:cat name`, clear with `gC` /
`:cat!`. Names are lowercase: letters, digits, hyphens, 1–32 chars.

## Cards

`N CardName [@category] [#tag …]`

- `N` is the quantity. If omitted, vimtg assumes `1` on parse and writes it
  back explicitly.
- `CardName` is the canonical Scryfall name. Double-faced cards use `//` as
  the separator (`Bonecrusher Giant // Stomp`).
- The optional `@category` token follows the name after two spaces.
- Tags follow and are space-separated `#word` tokens. They are
  stored deck-locally and never sent to Scryfall.
- An inline comment may follow, introduced by two spaces and `//`
  (`4 Bolt  @removal  #burn  // best card`). Canonical order is name,
  category, tags, comment.
  The two-space delimiter keeps double-faced names (`Fire // Ice`, single
  spaces) unambiguous. Add or edit a comment with `A` in the editor.

## Sideboard

Any line prefixed with `SB:` belongs to the sideboard. The prefix can be
preceded by whitespace.

```
SB: 2 Rest in Peace
SB: 3 Kor Firewalker
```

A `// Sideboard` header is conventional but not required — the `SB:` prefix
is what counts.

## Other zones

The same prefix convention covers the remaining zones:

- `MB:` — maybeboard, a scratchpad outside the deck (never counted
  toward deck size or copy limits; legality issues are warnings).
- `CMD:` — the command zone. Commander entries count toward the
  format's exact 100 and the singleton rule; at most two (partners),
  quantity 1 each.
- `CMP:` — the companion slot. At most one, quantity 1, outside the
  deck proper; the card must actually have the Companion ability.

In the editor, `ms`/`mm`/`md`/`mc`/`mp` move the cursor card between
zones.

## Zone block headers (Python style)

Every zone can also be written Python-style: the zone name alone on a
line, with its cards indented beneath it. Bare card lines indented under
the header belong to that zone — no per-line prefix needed. This reads
especially well for the commander, and for partner pairs:

```
CMD:
    1 Thrasios, Triton Hero
    1 Tymna the Weaver

DCK:
    1 Cultivate
    1 Sol Ring
```

Block rules, Python-like:

- A bare `DCK:` / `CMD:` / `CMP:` / `SB:` / `MB:` line opens the block
  (case-insensitive; `DCK: 4 Bolt` is a normal line, not a header).
- Indented lines are inside the block; blank lines are neutral.
- Any unindented non-blank line closes the block.
- An explicit prefix always wins: `SB: 1 Duress` is sideboard even
  inside a `CMD:` block.

Block style is the default: new decks scaffold a `DCK:` body (plus a
`CMD:` block for commander decks), a zone move that creates a brand-new
zone opens it as a block, and auto-sorted inserts create their
`// Creature`-style type headers indented inside the `DCK:` block. Zone
moves and card inserts match the style of where they land — indented
inside blocks, prefixed next to prefix-style entries. Layout regrouping
(`:layout`, `gl`) preserves each zone's style; export normalizes to
prefix style. Bare zone headers are structural declarations and are
never removed by section cleanup (derived type/category headers are
still dropped when their zone's cards leave).

## Round-trip fidelity

vimtg's parser/writer round-trip:
- Section headers (preserved verbatim, including order)
- Blank lines between sections
- Card-line tag order (tags are sorted on write)
- Sideboard placement
- Metadata keys (unknown keys preserved)

What it does **not** preserve:
- Trailing whitespace on lines
- Tabs (replaced with spaces)
- Comment-only sections that contain no cards (collapsed)

## Example

```
// Deck: Burn
// Format: modern

// Creatures
4 Goblin Guide #threat
4 Monastery Swiftspear #threat
4 Eidolon of the Great Revel #threat

// Spells
4 Lightning Bolt #removal #burn
4 Searing Blaze #burn
4 Skullcrack #burn
4 Boros Charm #flex

// Lands
4 Inspiring Vantage
4 Sacred Foundry
8 Mountain

// Sideboard
SB: 2 Rest in Peace
SB: 3 Kor Firewalker
SB: 2 Smash to Smithereens
SB: 3 Path to Exile
SB: 2 Skullcrack
SB: 3 Searing Blood
```

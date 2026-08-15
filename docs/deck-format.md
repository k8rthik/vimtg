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
| Section header | `// header text` | `// Creatures` |
| Card entry | `[N] CardName [#tag …] [// comment]` | `4 Lightning Bolt  #removal  // core` |
| Sideboard entry | `SB: [N] CardName [#tag …] [// comment]` | `SB: 2 Rest in Peace` |
| Blank | (empty) | |

## Metadata keys

Recognized at the top of the file:

| Key | Meaning |
|-----|---------|
| `Deck` | Deck name (used in greeter, history) |
| `Format` | Format name (`modern`, `legacy`, `commander`, …) |
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

Any `// text` line that isn't a recognized metadata key is treated as a
section header. Sections are purely visual — they affect rendering and the
`{` / `}` motions but have no semantic meaning.

```
// Creatures
4 Goblin Guide
4 Monastery Swiftspear

// Spells
4 Lightning Bolt
```

## Cards

`N CardName [#tag …]`

- `N` is the quantity. If omitted, vimtg assumes `1` on parse and writes it
  back explicitly.
- `CardName` is the canonical Scryfall name. Double-faced cards use `//` as
  the separator (`Bonecrusher Giant // Stomp`).
- Tags follow the name and are space-separated `#word` tokens. They are
  stored deck-locally and never sent to Scryfall.
- An inline comment may follow, introduced by two spaces and `//`
  (`4 Bolt  #burn  // best card`). Canonical order is name, tags, comment.
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

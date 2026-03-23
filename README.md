# vimtg

Vim-powered Magic: The Gathering deck builder for the terminal.

## Install

    pip install vimtg

## Quick Start

    vimtg sync                    # Download card database (~35MB)
    vimtg edit my-deck.deck       # Open deck editor
    vimtg search "lightning bolt" # Search cards

## Features

- **Vim keybindings** -- hjkl, dd/yy/p, visual mode, macros, registers
- **Offline card search** -- 30,000+ cards searchable in <50ms
- **Plain text decks** -- Git-friendly .deck format
- **Inline card details** -- Auto-expanding oracle text follows your cursor
- **Undo tree** -- Branch and checkpoint deck iterations
- **Bulk operations** -- `:g/t:creature/d`, `:%s/Bolt/Helix/g`
- **Import/export** -- MTGO, Arena, Moxfield, Archidekt formats
- **Deck analytics** -- Mana curve, color distribution, price totals

## Deck Format

    // Deck: Burn
    // Format: modern

    // Creatures
    4 Goblin Guide
    4 Monastery Swiftspear

    // Spells
    4 Lightning Bolt

    // Sideboard
    SB: 2 Rest in Peace

## Commands

| Command | Description |
|---------|-------------|
| `:w` | Save deck |
| `:q` | Quit (`:q!` force) |
| `:sort cmc` | Sort by mana cost |
| `:%s/old/new/g` | Substitute |
| `:g/pattern/d` | Delete matching |
| `:export arena` | Export format |
| `:help` | Show help |

## License

MIT

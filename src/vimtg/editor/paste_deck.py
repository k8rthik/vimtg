"""Add a pasted decklist to the buffer — TUI-agnostic, zero Textual imports.

Pasting text in normal mode parses it with the importer's decklist
parser (Arena, MTGO, Moxfield/Archidekt CSV, vimtg — auto-detected) and
merges every entry into its own zone: a card the zone already has gains
the copies, a new main-deck card goes where the placement policy files
it (type or category section), and a sideboard/commander/... card goes
into that zone's block. The caller records the whole paste as one undo
step.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from vimtg.domain.deck import Deck, DeckSection
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.operators import ALPHA_ZONES, insert_zone_line
from vimtg.editor.placement import PlacementPolicy, place_mainboard_card

SECTION_ZONES = {
    DeckSection.MAIN: LineType.CARD_ENTRY,
    DeckSection.SIDEBOARD: LineType.SIDEBOARD_ENTRY,
    DeckSection.MAYBEBOARD: LineType.MAYBEBOARD_ENTRY,
    DeckSection.COMMANDER: LineType.COMMANDER_ENTRY,
    DeckSection.COMPANION: LineType.COMPANION_ENTRY,
}

# Card name -> its type line, when the card database knows it
TypeLookup = Callable[[str], str | None]


@dataclass(frozen=True)
class PasteResult:
    buffer: Buffer
    first_row: int | None  # row of the first card touched (cursor target)
    cards: int  # copies added, over all entries


def _find_line(buffer: Buffer, name: str, zone: LineType) -> int | None:
    key = name.casefold()
    for i in range(buffer.line_count()):
        if buffer.get_line(i).line_type != zone:
            continue
        existing = buffer.card_name_at(i)
        if existing is not None and existing.casefold() == key:
            return i
    return None


def add_deck_entries(
    buffer: Buffer,
    deck: Deck,
    *,
    auto_sort: bool,
    type_line: TypeLookup = lambda _name: None,
) -> PasteResult:
    """Merge every entry of `deck` into `buffer` (see module doc)."""
    cards = 0
    for entry in deck.entries:
        zone = SECTION_ZONES[entry.section]
        existing = _find_line(buffer, entry.card_name, zone)
        if existing is not None:
            qty = buffer.quantity_at(existing) or 0
            buffer = buffer.set_quantity(existing, qty + entry.quantity)
        elif zone == LineType.CARD_ENTRY:
            policy = PlacementPolicy(
                auto_sort=auto_sort, type_line=type_line(entry.card_name)
            )
            placed = place_mainboard_card(buffer, policy, category=entry.category)
            line = f"{placed.indent}{entry.quantity} {entry.card_name}"
            buffer = placed.buffer.insert_line(placed.row, line)
            if placed.category:
                buffer = buffer.set_category(placed.row, placed.category)
        else:
            sort_name = entry.card_name if auto_sort and zone in ALPHA_ZONES else None
            buffer, _row, _ = insert_zone_line(
                buffer, zone, f"{entry.quantity} {entry.card_name}", sort_name=sort_name
            )
        cards += entry.quantity
    # Looked up at the end: later inserts (and new headers) shift rows
    first_row = None
    if deck.entries:
        first = deck.entries[0]
        first_row = _find_line(buffer, first.card_name, SECTION_ZONES[first.section])
    return PasteResult(buffer, first_row, cards)

"""The cards a user owns, and a deck's ownership against them.

A :class:`Collection` comes from a vendor CSV export (ManaBox, Moxfield,
Archidekt, Deckbox, or any file with a name and a count column). vimtg
does not track printings, so every row of one card sums into one count,
keyed the way the deck parser and the card repository match names:
through :func:`vimtg.domain.card_names.name_aliases`, so "Fire/Ice",
"Fire // Ice" and a front-face-only "Bonecrusher Giant" all meet.

:func:`ownership` allots that count to the deck's entries, one pool per
card across zones, and :func:`summarize_ownership` and
:func:`missing_list` derive what the user sees: owned/missing totals,
the cost to complete, and the shopping list.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from vimtg.domain.card import Card
from vimtg.domain.card_names import name_aliases, normalize_card_name
from vimtg.domain.csv_rows import (
    COUNT_HEADERS,
    NAME_HEADERS,
    card_name_cell,
    count_cell,
    find_column,
)
from vimtg.domain.deck import Deck, DeckEntry, DeckSection
from vimtg.domain.deck_lines import MAX_QUANTITY, strip_bom


class CollectionError(ValueError):
    """A collection file that cannot be used, with the reason a user can act on."""


@dataclass(frozen=True)
class Collection:
    """Owned copies per card, summed across printings.

    `owned` is keyed by every alias of each card name (see
    :func:`name_aliases`); use :meth:`owned_count` rather than indexing.
    """

    owned: Mapping[str, int]
    total_cards: int
    unique_cards: int
    skipped_rows: int
    source: Path
    loaded_at: datetime

    def owned_count(self, name: str) -> int:
        """Copies owned of the card `name` names, under any spelling."""
        for key, _rank in name_aliases(name):
            count = self.owned.get(key)
            if count is not None:
                return count
        return 0

    def status(self) -> str:
        """'Collection: 54 cards (31 unique) from manabox.csv[, 2 rows skipped]'."""
        text = (
            f"Collection: {self.total_cards} cards ({self.unique_cards} unique) "
            f"from {self.source.name}"
        )
        if self.skipped_rows:
            plural = "" if self.skipped_rows == 1 else "s"
            text += f", {self.skipped_rows} row{plural} skipped"
        return text


def parse_collection_csv(
    text: str, source: Path, loaded_at: datetime | None = None
) -> Collection:
    """Parse a collection CSV export.

    Header matching is case-insensitive; a file with no recognisable
    name or count column raises :class:`CollectionError` naming the
    headers it found. A row whose name is empty or whose count is not a
    positive integer is skipped and counted.
    """
    reader = csv.DictReader(io.StringIO(strip_bom(text)))
    fieldnames = reader.fieldnames
    name_col = find_column(fieldnames, NAME_HEADERS)
    count_col = find_column(fieldnames, COUNT_HEADERS)
    if name_col is None or count_col is None:
        found = ", ".join(fieldnames) if fieldnames else "no header row"
        raise CollectionError(
            f"{source.name} has no {'card name' if name_col is None else 'count'} "
            f"column (found: {found}; expected one of "
            f"{', '.join(NAME_HEADERS)} and one of {', '.join(COUNT_HEADERS)})"
        )

    # Alias key -> (rank, copies). A full name (rank 0) owns its key;
    # a face name only fills a key no full name claimed.
    ranked: dict[str, tuple[int, int]] = {}
    full_names: set[str] = set()
    total = 0
    skipped = 0
    for row in reader:
        name = card_name_cell(row, name_col)
        count = count_cell(row, count_col)
        if not name or count is None or count <= 0:
            if any((v or "").strip() for v in row.values() if isinstance(v, str)):
                skipped += 1
            continue
        count = min(count, MAX_QUANTITY)
        total += count
        full_names.add(normalize_card_name(name))
        for key, rank in name_aliases(name):
            existing = ranked.get(key)
            if existing is None or rank < existing[0]:
                ranked[key] = (rank, count)
            elif rank == existing[0]:
                ranked[key] = (rank, existing[1] + count)

    return Collection(
        owned=MappingProxyType({key: copies for key, (_rank, copies) in ranked.items()}),
        total_cards=total,
        unique_cards=len(full_names),
        skipped_rows=skipped,
        source=source,
        loaded_at=loaded_at or datetime.now(),
    )


# Zones a deck needs cards for, in the order the owned pool is allotted
_COUNTED_ZONES: tuple[DeckSection, ...] = (
    DeckSection.COMMANDER,
    DeckSection.COMPANION,
    DeckSection.MAIN,
    DeckSection.SIDEBOARD,
)


@dataclass(frozen=True)
class Ownership:
    """One deck entry against the collection: `owned` is the share of the
    card's pool allotted to this entry (main before sideboard)."""

    entry: DeckEntry
    owned: int

    @property
    def needed(self) -> int:
        return self.entry.quantity

    @property
    def missing(self) -> int:
        return max(0, self.needed - self.owned)


def ownership(deck: Deck, collection: Collection) -> tuple[Ownership, ...]:
    """Every counted entry's ownership, in deck order.

    Entries naming the same card share one owned pool, allotted
    commander, companion, mainboard, then sideboard. Maybeboard
    entries are not needed and get none.
    """
    remaining: dict[str, int] = {}
    allotted: dict[int, int] = {}
    counted = [
        (i, e) for i, e in enumerate(deck.entries) if e.section in _COUNTED_ZONES
    ]
    for zone in _COUNTED_ZONES:
        for i, entry in counted:
            if entry.section is not zone:
                continue
            key = normalize_card_name(entry.card_name)
            if key not in remaining:
                remaining[key] = collection.owned_count(entry.card_name)
            share = min(remaining[key], entry.quantity)
            remaining[key] -= share
            allotted[i] = share
    return tuple(Ownership(entry, allotted[i]) for i, entry in counted)


@dataclass(frozen=True)
class OwnershipSummary:
    """Deck-level ownership totals for the analytics pane and the CLI."""

    needed_cards: int
    owned_cards: int
    missing_cards: int
    missing_unique: int
    # Sum of `price_source` prices over the missing copies that have one;
    # None when no missing card is priced
    cost_to_complete: float | None
    unpriced_unique: int  # missing cards without a `price_source` price
    price_source: str


def summarize_ownership(
    owns: Iterable[Ownership], resolved: Mapping[str, Card], price_source: str
) -> OwnershipSummary:
    """Totals over `owns`; prices come from `resolved` (the deck's cards
    by name, as :meth:`CardRepository.get_by_names` returns them)."""
    needed = owned = 0
    missing_by_card: dict[str, int] = {}
    for own in owns:
        needed += own.needed
        owned += own.owned
        if own.missing:
            key = normalize_card_name(own.entry.card_name)
            missing_by_card[key] = missing_by_card.get(key, 0) + own.missing
    cost = 0.0
    priced = False
    unpriced: set[str] = set()
    for own in owns:
        if not own.missing:
            continue
        card = resolved.get(own.entry.card_name)
        price = card.prices.get(price_source) if card is not None else None
        if price is None:
            unpriced.add(normalize_card_name(own.entry.card_name))
            continue
        cost += price * own.missing
        priced = True
    return OwnershipSummary(
        needed_cards=needed,
        owned_cards=owned,
        missing_cards=needed - owned,
        missing_unique=len(missing_by_card),
        cost_to_complete=round(cost, 2) if priced else None,
        unpriced_unique=len(unpriced),
        price_source=price_source,
    )


def missing_list(owns: Iterable[Ownership], resolved: Mapping[str, Card]) -> str:
    """The missing cards as 'N Card Name' lines a store's mass-entry box
    accepts: the mainboard (with commander and companion), a blank line,
    then the sideboard. One line per card; empty blocks are left out,
    and '' when nothing is missing. Names are the official ones when
    `resolved` knows the card."""
    blocks: dict[bool, dict[str, tuple[str, int]]] = {False: {}, True: {}}
    for own in owns:
        if not own.missing:
            continue
        block = blocks[own.entry.section is DeckSection.SIDEBOARD]
        key = normalize_card_name(own.entry.card_name)
        card = resolved.get(own.entry.card_name)
        name = card.name if card is not None else own.entry.card_name
        shown, count = block.get(key, (name, 0))
        block[key] = (shown, count + own.missing)
    parts = [
        "".join(f"{count} {name}\n" for name, count in block.values())
        for block in (blocks[False], blocks[True])
        if block
    ]
    return "\n".join(parts)

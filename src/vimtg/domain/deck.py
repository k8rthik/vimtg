"""Deck domain model — pure data, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class DeckSection(Enum):
    MAIN = "main"
    SIDEBOARD = "sideboard"
    COMMANDER = "commander"
    COMPANION = "companion"


@dataclass(frozen=True)
class DeckEntry:
    quantity: int
    card_name: str
    section: DeckSection


@dataclass(frozen=True)
class CommentLine:
    line_number: int
    text: str


@dataclass(frozen=True)
class DeckMetadata:
    name: str = ""
    format: str = ""
    author: str = ""
    description: str = ""


@dataclass(frozen=True)
class Deck:
    metadata: DeckMetadata
    entries: tuple[DeckEntry, ...]
    comments: tuple[CommentLine, ...]

    def total_cards(self) -> int:
        return sum(e.quantity for e in self.entries)

    def mainboard(self) -> tuple[DeckEntry, ...]:
        return tuple(
            e for e in self.entries if e.section == DeckSection.MAIN
        )

    def sideboard(self) -> tuple[DeckEntry, ...]:
        return tuple(
            e for e in self.entries if e.section == DeckSection.SIDEBOARD
        )

    def unique_card_names(self) -> frozenset[str]:
        return frozenset(e.card_name for e in self.entries)

    def add_entry(self, entry: DeckEntry) -> Deck:
        """Add an entry. If same card+section exists, increment quantity.

        Returns a NEW Deck; original is unchanged.
        """
        new_entries: list[DeckEntry] = []
        found = False
        for existing in self.entries:
            if (
                existing.card_name == entry.card_name
                and existing.section == entry.section
            ):
                merged = replace(
                    existing,
                    quantity=existing.quantity + entry.quantity,
                )
                new_entries.append(merged)
                found = True
            else:
                new_entries.append(existing)

        if not found:
            new_entries.append(entry)

        return replace(self, entries=tuple(new_entries))

    def remove_entry(
        self, card_name: str, section: DeckSection
    ) -> Deck:
        """Remove entry by card name and section.

        Returns a NEW Deck. If not found, returns Deck with same entries.
        """
        new_entries = tuple(
            e
            for e in self.entries
            if not (e.card_name == card_name and e.section == section)
        )
        return replace(self, entries=new_entries)

    def update_quantity(
        self, card_name: str, section: DeckSection, quantity: int
    ) -> Deck:
        """Update quantity for a card. Removes entry if quantity <= 0.

        Returns a NEW Deck.
        """
        if quantity <= 0:
            return self.remove_entry(card_name, section)

        new_entries = tuple(
            replace(e, quantity=quantity)
            if (e.card_name == card_name and e.section == section)
            else e
            for e in self.entries
        )
        return replace(self, entries=new_entries)

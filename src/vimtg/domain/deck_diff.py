"""MTG-aware semantic diff engine for decklists.

Computes card-level changes (added, removed, quantity changed, section moved)
between two deck states. Operates on parsed Deck objects rather than raw text,
so diffs are meaningful to MTG players — not line-level noise.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.deck import DeckSection


class ChangeType(Enum):
    """Classification of a single card change between two deck states."""

    ADDED = "added"
    REMOVED = "removed"
    QUANTITY_CHANGED = "quantity_changed"
    SECTION_MOVED = "section_moved"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class CardChange:
    """A single card-level change between two deck states."""

    card_name: str
    change_type: ChangeType
    section: DeckSection
    old_quantity: int | None = None
    new_quantity: int | None = None
    old_section: DeckSection | None = None
    new_section: DeckSection | None = None


@dataclass(frozen=True)
class StatsDelta:
    """Stats comparison between two deck states."""

    old_total: int
    new_total: int
    old_avg_cmc: float
    new_avg_cmc: float
    old_price: float | None
    new_price: float | None
    curve_delta: dict[int, int]


@dataclass(frozen=True)
class DeckDiff:
    """Complete MTG-aware diff between two deck states."""

    changes: tuple[CardChange, ...]
    stats_delta: StatsDelta | None = None

    @property
    def mainboard_changes(self) -> tuple[CardChange, ...]:
        return tuple(
            c for c in self.changes
            if c.section == DeckSection.MAIN
            or c.old_section == DeckSection.MAIN
            or c.new_section == DeckSection.MAIN
        )

    @property
    def sideboard_changes(self) -> tuple[CardChange, ...]:
        return tuple(
            c for c in self.changes
            if c.section == DeckSection.SIDEBOARD
            or c.old_section == DeckSection.SIDEBOARD
            or c.new_section == DeckSection.SIDEBOARD
        )

    @property
    def has_changes(self) -> bool:
        return any(c.change_type != ChangeType.UNCHANGED for c in self.changes)

    @property
    def added_count(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.ADDED)

    @property
    def removed_count(self) -> int:
        return sum(1 for c in self.changes if c.change_type == ChangeType.REMOVED)


def _build_card_map(
    deck_text: str,
) -> dict[str, tuple[int, DeckSection]]:
    """Parse deck text and return {card_name: (quantity, section)} dict."""
    deck = parse_deck_text(deck_text)
    result: dict[str, tuple[int, DeckSection]] = {}
    for entry in deck.entries:
        result[entry.card_name] = (entry.quantity, entry.section)
    return result


def compute_deck_diff(old_state: str, new_state: str) -> DeckDiff:
    """Compute card-level diff between two deck state strings.

    Returns a DeckDiff with CardChange entries for every card that was
    added, removed, had its quantity changed, or moved between sections.
    Unchanged cards are included too (marked UNCHANGED) for complete rendering.
    """
    old_map = _build_card_map(old_state)
    new_map = _build_card_map(new_state)

    all_cards = sorted(set(old_map) | set(new_map))
    changes: list[CardChange] = []

    for card_name in all_cards:
        old_entry = old_map.get(card_name)
        new_entry = new_map.get(card_name)

        if old_entry is None and new_entry is not None:
            # Card added
            new_qty, new_sec = new_entry
            changes.append(CardChange(
                card_name=card_name,
                change_type=ChangeType.ADDED,
                section=new_sec,
                new_quantity=new_qty,
                new_section=new_sec,
            ))
        elif old_entry is not None and new_entry is None:
            # Card removed
            old_qty, old_sec = old_entry
            changes.append(CardChange(
                card_name=card_name,
                change_type=ChangeType.REMOVED,
                section=old_sec,
                old_quantity=old_qty,
                old_section=old_sec,
            ))
        elif old_entry is not None and new_entry is not None:
            old_qty, old_sec = old_entry
            new_qty, new_sec = new_entry

            if old_sec != new_sec:
                # Card moved between sections
                changes.append(CardChange(
                    card_name=card_name,
                    change_type=ChangeType.SECTION_MOVED,
                    section=new_sec,
                    old_quantity=old_qty,
                    new_quantity=new_qty,
                    old_section=old_sec,
                    new_section=new_sec,
                ))
            elif old_qty != new_qty:
                # Quantity changed
                changes.append(CardChange(
                    card_name=card_name,
                    change_type=ChangeType.QUANTITY_CHANGED,
                    section=old_sec,
                    old_quantity=old_qty,
                    new_quantity=new_qty,
                ))
            else:
                # Unchanged
                changes.append(CardChange(
                    card_name=card_name,
                    change_type=ChangeType.UNCHANGED,
                    section=old_sec,
                    old_quantity=old_qty,
                    new_quantity=new_qty,
                ))

    return DeckDiff(changes=tuple(changes))

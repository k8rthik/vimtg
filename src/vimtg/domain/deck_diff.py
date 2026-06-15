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
) -> dict[tuple[str, DeckSection], int]:
    """Parse deck text into {(card_name, section): total_quantity}.

    Keying by (name, section) — rather than name alone — keeps a card that
    appears in more than one section (e.g. main and sideboard) from collapsing
    into a single entry. Duplicate lines for the same card+section are summed.
    """
    deck = parse_deck_text(deck_text)
    result: dict[tuple[str, DeckSection], int] = {}
    for entry in deck.entries:
        key = (entry.card_name, entry.section)
        result[key] = result.get(key, 0) + entry.quantity
    return result


def _sections_by_name(
    card_map: dict[tuple[str, DeckSection], int],
) -> dict[str, set[DeckSection]]:
    """Group the sections each card name occupies."""
    out: dict[str, set[DeckSection]] = {}
    for name, section in card_map:
        out.setdefault(name, set()).add(section)
    return out


def compute_deck_diff(old_state: str, new_state: str) -> DeckDiff:
    """Compute card-level diff between two deck state strings.

    Returns a DeckDiff with CardChange entries for every card that was
    added, removed, had its quantity changed, or moved between sections.
    Unchanged cards are included too (marked UNCHANGED) for complete rendering.

    A card living in a single section in both states that changed section is
    reported as one SECTION_MOVED. Any other arrangement (including a card
    present in two sections at once) is diffed independently per section.
    """
    old_map = _build_card_map(old_state)
    new_map = _build_card_map(new_state)
    old_sections = _sections_by_name(old_map)
    new_sections = _sections_by_name(new_map)

    changes: list[CardChange] = []
    moved_keys: set[tuple[str, DeckSection]] = set()

    # Single-section moves: name occupies exactly one (different) section in
    # each state. Handle these first and exclude their keys from the per-key
    # pass below.
    for name in sorted(set(old_sections) | set(new_sections)):
        old_secs = old_sections.get(name, set())
        new_secs = new_sections.get(name, set())
        if len(old_secs) == 1 and len(new_secs) == 1 and old_secs != new_secs:
            (old_sec,) = old_secs
            (new_sec,) = new_secs
            changes.append(CardChange(
                card_name=name,
                change_type=ChangeType.SECTION_MOVED,
                section=new_sec,
                old_quantity=old_map[(name, old_sec)],
                new_quantity=new_map[(name, new_sec)],
                old_section=old_sec,
                new_section=new_sec,
            ))
            moved_keys.add((name, old_sec))
            moved_keys.add((name, new_sec))

    all_keys = sorted(
        set(old_map) | set(new_map), key=lambda k: (k[0], k[1].value)
    )
    for key in all_keys:
        if key in moved_keys:
            continue
        name, section = key
        old_qty = old_map.get(key)
        new_qty = new_map.get(key)

        if old_qty is None and new_qty is not None:
            changes.append(CardChange(
                card_name=name,
                change_type=ChangeType.ADDED,
                section=section,
                new_quantity=new_qty,
                new_section=section,
            ))
        elif old_qty is not None and new_qty is None:
            changes.append(CardChange(
                card_name=name,
                change_type=ChangeType.REMOVED,
                section=section,
                old_quantity=old_qty,
                old_section=section,
            ))
        elif old_qty != new_qty:
            changes.append(CardChange(
                card_name=name,
                change_type=ChangeType.QUANTITY_CHANGED,
                section=section,
                old_quantity=old_qty,
                new_quantity=new_qty,
            ))
        else:
            changes.append(CardChange(
                card_name=name,
                change_type=ChangeType.UNCHANGED,
                section=section,
                old_quantity=old_qty,
                new_quantity=new_qty,
            ))

    return DeckDiff(changes=tuple(changes))

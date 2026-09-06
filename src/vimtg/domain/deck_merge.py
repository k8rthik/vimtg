"""Pure 3-way merge and change-replay logic for decklists.

Merging operates on card maps keyed by (card_name, section) — the same
identity key as the diff engine — with quantities as the merged values.
A conflict is a key both sides changed, differently, relative to the base.

Results round-trip through serialize_deck, which normalizes section
grouping. Freeform comments (including section headers like
"// Creatures") are dropped deliberately: serialize_deck would hoist
them above the card list, where the section-cleanup pass then deletes
or mislabels them — dropping is the lesser evil. Metadata survives.

TUI-agnostic: no Textual imports. No SQLite.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from vimtg.data.deck_repository import parse_deck_text, serialize_deck
from vimtg.domain.deck import Deck, DeckEntry, DeckSection
from vimtg.domain.deck_diff import CardChange, ChangeType, build_card_map

CardKey = tuple[str, DeckSection]


@dataclass(frozen=True)
class MergeConflict:
    """A card both sides changed, differently, relative to the base.

    A None quantity means the card is absent in that version.
    """

    card_name: str
    section: DeckSection
    base_quantity: int | None
    ours_quantity: int | None
    theirs_quantity: int | None

    @property
    def key(self) -> CardKey:
        return (self.card_name, self.section)


@dataclass(frozen=True)
class ThreeWayResult:
    """Outcome of a 3-way merge: auto-merged map plus unresolved conflicts.

    Conflicted keys are excluded from `merged` until resolved.
    """

    merged: dict[CardKey, int]
    conflicts: tuple[MergeConflict, ...]

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def three_way_merge(
    base_state: str, ours_state: str, theirs_state: str
) -> ThreeWayResult:
    """Merge two deck states against a common base, card by card.

    Per (card_name, section) key: if both sides agree, take that; if only
    one side changed relative to base, take the changed side (including
    deletions); if both changed differently, report a conflict.

    Section moves need no special handling — a move is a removal in the
    old section plus an addition in the new one, each resolved
    independently.
    """
    base = build_card_map(base_state)
    ours = build_card_map(ours_state)
    theirs = build_card_map(theirs_state)

    merged: dict[CardKey, int] = {}
    conflicts: list[MergeConflict] = []

    all_keys = sorted(
        set(base) | set(ours) | set(theirs), key=lambda k: (k[1].value, k[0])
    )
    for key in all_keys:
        b = base.get(key)
        o = ours.get(key)
        t = theirs.get(key)

        if o == t:
            result = o  # agreement (both changed identically, or neither)
        elif o == b:
            result = t  # only theirs changed
        elif t == b:
            result = o  # only ours changed
        else:
            name, section = key
            conflicts.append(MergeConflict(
                card_name=name,
                section=section,
                base_quantity=b,
                ours_quantity=o,
                theirs_quantity=t,
            ))
            continue

        if result is not None:
            merged[key] = result

    return ThreeWayResult(merged=merged, conflicts=tuple(conflicts))


def merged_map_to_deck_state(
    merged: dict[CardKey, int], ours_state: str
) -> str:
    """Serialize a merged card map, preserving our side's card order.

    Cards present in ours keep their position (and tags); keys only the
    other side contributed are appended, sorted by (section, name).
    Metadata comes from ours; freeform comments are dropped (see module
    docstring).
    """
    ours_deck = parse_deck_text(ours_state)
    remaining = dict(merged)
    entries: list[DeckEntry] = []

    for entry in ours_deck.entries:
        key = (entry.card_name, entry.section)
        if key not in remaining:
            continue  # dropped by the merge, or a duplicate line already emitted
        entries.append(replace(entry, quantity=remaining.pop(key)))

    for key in sorted(remaining, key=lambda k: (k[1].value, k[0])):
        name, section = key
        entries.append(DeckEntry(
            quantity=remaining[key], card_name=name, section=section,
        ))

    result_deck = Deck(
        metadata=ours_deck.metadata,
        entries=tuple(entries),
        comments=(),
        plans=ours_deck.plans,
    )
    return serialize_deck(result_deck)


def apply_card_changes(state: str, changes: Sequence[CardChange]) -> str:
    """Replay a sequence of card-level changes onto a deck state.

    Deterministic overlap policy: the replayed change wins (quantities are
    set, removals remove); an ADDED change is skipped only when the exact
    (card, section) key already exists. Used by cherry-pick and rebase.
    """
    deck = parse_deck_text(state)
    entries = list(deck.entries)

    for change in changes:
        if change.change_type is ChangeType.ADDED:
            exists = any(
                e.card_name == change.card_name and e.section == change.section
                for e in entries
            )
            if not exists and change.new_quantity:
                entries.append(DeckEntry(
                    quantity=change.new_quantity,
                    card_name=change.card_name,
                    section=change.section,
                ))
        elif change.change_type is ChangeType.REMOVED:
            entries = [
                e for e in entries
                if not (
                    e.card_name == change.card_name
                    and e.section == change.section
                )
            ]
        elif change.change_type is ChangeType.QUANTITY_CHANGED:
            if change.new_quantity is None:
                continue
            entries = [
                replace(e, quantity=change.new_quantity)
                if (
                    e.card_name == change.card_name
                    and e.section == change.section
                )
                else e
                for e in entries
            ]
        elif change.change_type is ChangeType.SECTION_MOVED:
            if change.old_section is None or change.new_section is None:
                continue
            entries = [
                e for e in entries
                if not (
                    e.card_name == change.card_name
                    and e.section == change.old_section
                )
            ]
            exists = any(
                e.card_name == change.card_name
                and e.section == change.new_section
                for e in entries
            )
            if not exists and change.new_quantity:
                entries.append(DeckEntry(
                    quantity=change.new_quantity,
                    card_name=change.card_name,
                    section=change.new_section,
                ))

    result_deck = Deck(
        metadata=deck.metadata,
        entries=tuple(entries),
        comments=(),
        plans=deck.plans,
    )
    return serialize_deck(result_deck)

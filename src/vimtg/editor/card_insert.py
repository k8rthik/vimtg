"""Confirming a card search: where the chosen card is written.

The o/O/c card search ends here. The TUI picks the card; this module
writes it into the buffer at the zone the cursor is in, so the live
confirm and a dot-repeat replay of it run the same code.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vimtg.editor.buffer import Buffer, LineType, insertion_zone
from vimtg.editor.operators import (
    ALPHA_ZONES,
    ZONE_LABELS,
    insert_zone_line,
    zone_line_text,
)
from vimtg.editor.placement import PlacementPolicy, place_mainboard_card
from vimtg.editor.sections import matched_indent

if TYPE_CHECKING:
    from vimtg.domain.card import Card
    from vimtg.editor.session import EditorState


@dataclass(frozen=True)
class PendingInsert:
    """The transient blank line an o/O opened for card search.

    `row` is where the blank sits; `origin` is the cursor row before
    the open, so cancelling can put the cursor back exactly.
    """

    row: int
    origin: int


def find_card_line(
    buffer: Buffer, card_name: str, zone: LineType | None = None
) -> int | None:
    """Find an existing line with this card name in `zone`.

    Duplicate detection is zone-scoped: adding a card where the cursor
    is must increment a copy in THAT zone, never one in another zone.
    Defaults to the mainboard.
    """
    target = zone if zone is not None else LineType.CARD_ENTRY
    for i in range(buffer.line_count()):
        if (
            buffer.get_line(i).line_type == target
            and buffer.card_name_at(i) == card_name
        ):
            return i
    return None


def open_insert_line(state: EditorState, variant: str) -> None:
    """Apply buffer changes for insert mode variants (o, O).

    On a metadata line ('// Deck:', '// Format:', ...) both o and O
    open the line below the whole block instead — a card line must
    never split the metadata header.
    """
    # Defensive: a cursor trailing a shrunken buffer opens at its end
    row = max(0, min(state.cursor.row, state.buffer.line_count() - 1))
    origin = row
    if state.buffer.get_line(row).line_type == LineType.METADATA:
        while (
            row < state.buffer.line_count()
            and state.buffer.get_line(row).line_type == LineType.METADATA
        ):
            row += 1
        state.buffer = state.buffer.insert_line(row, "")
        state.cursor = state.cursor.move_to(row, 0)
        state.pending_insert = PendingInsert(row=row, origin=origin)
        return
    if variant == "o":
        state.buffer = state.buffer.insert_line(row + 1, "")
        state.cursor = state.cursor.move_to(row + 1, 0)
        state.pending_insert = PendingInsert(row=row + 1, origin=origin)
    elif variant == "O":
        state.buffer = state.buffer.insert_line(row, "")
        state.pending_insert = PendingInsert(row=row, origin=origin)


def discard_pending_insert(state: EditorState) -> None:
    """Cancel path: remove the scratch blank an o/O opened, if it is
    still there and still blank, and put the cursor back on the line
    it was opened from. No-op when nothing is pending."""
    pend = state.pending_insert
    state.pending_insert = None
    state.pending_change = None  # a cancelled search records no card
    state.change_node = None
    if pend is None or pend.row >= state.buffer.line_count():
        return
    if state.buffer.get_line(pend.row).text.strip():
        return  # gained content some other way — never delete it
    state.buffer, _ = state.buffer.delete_lines(pend.row, pend.row)
    last = state.buffer.line_count() - 1
    state.cursor = state.cursor.move_to(max(0, min(pend.origin, last)), 0)


def take_insert_position(state: EditorState) -> tuple[int, bool]:
    """Confirm path: remove the scratch blank and return where the
    insert was opened, as (row, scratch_removed).

    With no pending scratch (cc deleted its line outright) the cursor
    row is the place the confirmed card belongs — returned with
    scratch_removed False so callers skip row adjustments.
    """
    pend = state.pending_insert
    state.pending_insert = None
    if (
        pend is not None
        and pend.row < state.buffer.line_count()
        and not state.buffer.get_line(pend.row).text.strip()
    ):
        state.buffer, _ = state.buffer.delete_lines(pend.row, pend.row)
        return pend.row, True
    return state.cursor.row, False


def place_new_card(
    state: EditorState, card: Card | None, name: str, qty: int, open_row: int | None
) -> int:
    """Write a fresh mainboard line where the placement policy says
    (type section, category section, or where it was opened) and
    return its row. Stamps the category the section implies."""
    policy = PlacementPolicy(
        auto_sort=state.settings.auto_sort,
        type_line=card.type_line if card is not None else None,
    )
    placed = place_mainboard_card(state.buffer, policy, open_row=open_row)
    state.buffer = placed.buffer.insert_line(placed.row, f"{placed.indent}{qty} {name}")
    if placed.category:
        state.buffer = state.buffer.set_category(placed.row, placed.category)
    return placed.row


def _insert_plan_entry(state: EditorState, name: str, qty: int) -> None:
    """Write a signed plan line where the user opened it: '+N' for a
    card the sideboard holds, '-N' for a mainboard card (a card in
    neither zone gets '+' and a lint error)."""
    open_row, _ = take_insert_position(state)
    buf = state.buffer
    sign = (
        "+" if find_card_line(buf, name, LineType.SIDEBOARD_ENTRY) is not None
        else "-" if find_card_line(buf, name, LineType.CARD_ENTRY) is not None
        else "+"
    )
    indent = matched_indent(buf, open_row)
    state.buffer = buf.insert_line(open_row, f"{indent}{sign}{qty} {name}")
    state.cursor = state.cursor.move_to(open_row, 0)


def _insert_zone_card(state: EditorState, name: str, zone: LineType, qty: int) -> None:
    """Add a card to a non-main zone. With auto-sort on, sideboard
    and maybeboard lines stay alphabetical; otherwise (and for the
    commander/companion zones, where order matters) the card lands
    where the line was opened, in the zone's own style."""
    open_row, _ = take_insert_position(state)
    body = f"{qty} {name}"
    if state.settings.auto_sort and zone in ALPHA_ZONES:
        state.buffer, dest_row, _count = insert_zone_line(
            state.buffer, zone, body, sort_name=name
        )
        state.cursor = state.cursor.move_to(dest_row, 0)
        return
    text = zone_line_text(state.buffer, open_row, zone, body)
    state.buffer = state.buffer.insert_line(open_row, text)
    state.cursor = state.cursor.move_to(open_row, 0)


def insert_card(
    state: EditorState,
    name: str,
    card: Card | None,
    copies: int,
    *,
    fold_into: str | None = None,
) -> str:
    """Write `copies` of the chosen card where the card search was
    opened and return the status message.

    The cursor's zone decides where the card goes: opening a line inside
    the CMD:/SB: block (or among prefix lines of a zone) adds the card
    to THAT zone. A card the zone already holds gains copies instead of
    a second line. Records the undo step; the caller re-resolves cards.

    `fold_into` is the id of the undo node a c operator made by deleting
    the lines this card replaces: while that node is still current the
    card joins it, so one u undoes the whole change (vim's cc).
    """
    s = state
    zone = insertion_zone(s.buffer, s.cursor.row)
    duplicate_line = (
        None if zone == LineType.PLAN_ENTRY else find_card_line(s.buffer, name, zone)
    )
    if zone == LineType.PLAN_ENTRY:
        _insert_plan_entry(s, name, copies)
    elif duplicate_line is not None:
        qty = s.buffer.quantity_at(duplicate_line) or 0
        s.buffer = s.buffer.set_quantity(duplicate_line, qty + copies)
        open_row, removed = take_insert_position(s)
        if removed and duplicate_line > open_row:
            duplicate_line -= 1
        s.cursor = s.cursor.move_to(min(duplicate_line, s.buffer.line_count() - 1), 0)
    elif zone != LineType.CARD_ENTRY:
        _insert_zone_card(s, name, zone, copies)
    else:
        # Remove the scratch blank BEFORE the placement math —
        # creating a header can shift rows past a stale cursor
        open_row, _ = take_insert_position(s)
        row = place_new_card(s, card, name, copies, open_row)
        s.cursor = s.cursor.move_to(row, 0)
    s.modified = True
    if fold_into is not None and s.history.current_id == fold_into:
        s.history.amend(s.buffer)
    else:
        s.history.record(s.buffer, f"added {name}")
    zone_note = (
        f" to {ZONE_LABELS[zone]}"
        if zone not in (LineType.CARD_ENTRY, LineType.PLAN_ENTRY)
        else ""
    )
    added = f"{copies}x {name}" if copies > 1 else name
    return f"Added {added}{zone_note}  (+/- to change qty, dd to remove)"

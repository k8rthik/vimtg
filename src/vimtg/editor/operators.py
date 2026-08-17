"""Pure-function vim-style operators for editing a deck buffer.

Supports d/y/c (delete/yank/change) with motions, p/P (put),
and +/- (increment/decrement card quantity).

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from vimtg.domain.deck_lines import (
    CARD_PATTERN,
    format_inline_comment,
    parse_zone_header,
)
from vimtg.domain.tags import format_inline_tags
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.cursor import Cursor
from vimtg.editor.motions import MOTION_REGISTRY
from vimtg.editor.registers import RegisterStore


@dataclass(frozen=True)
class OperatorResult:
    buffer: Buffer
    cursor: Cursor
    registers: RegisterStore
    enter_insert: bool = False


def resolve_line_range(
    op: str, motion: str | None, cursor: Cursor, buffer: Buffer, count: int
) -> tuple[int, int]:
    """Resolve operator+motion to a line range (start, end inclusive).

    dd/yy/cc (motion=None) -> (cursor.row, cursor.row + count - 1)
    d+motion -> (cursor.row, motion_target.row) sorted
    """
    if motion is None:  # doubled operator: dd, yy, cc
        end = min(cursor.row + count - 1, buffer.line_count() - 1)
        return (cursor.row, end)
    motion_fn = MOTION_REGISTRY.get(motion)
    if motion_fn is None:
        return (cursor.row, cursor.row)
    target = motion_fn(cursor, buffer, count)
    start = min(cursor.row, target.row)
    end = max(cursor.row, target.row)
    return (start, end)


def execute_operator(
    op: str,
    motion: str | None,
    cursor: Cursor,
    buffer: Buffer,
    count: int,
    registers: RegisterStore,
    register_name: str | None = None,
) -> OperatorResult:
    """Execute d/y/c/dd/yy/cc with motion resolution."""
    # Normalize doubled ops: "dd" -> op="d", motion=None
    actual_op = op[0] if len(op) == 2 else op
    actual_motion = None if len(op) == 2 else motion

    start, end = resolve_line_range(actual_op, actual_motion, cursor, buffer, count)
    start = max(0, start)
    end = min(end, buffer.line_count() - 1)

    if actual_op == "y":
        return _yank(buffer, cursor, registers, register_name, start, end)

    if actual_op in ("d", "c"):
        return _delete_or_change(
            actual_op, buffer, cursor, registers, register_name, start, end
        )

    return OperatorResult(buffer=buffer, cursor=cursor, registers=registers)


def _yank(
    buffer: Buffer,
    cursor: Cursor,
    registers: RegisterStore,
    register_name: str | None,
    start: int,
    end: int,
) -> OperatorResult:
    """Yank lines into register without modifying buffer."""
    yanked = tuple(buffer.get_line(i).text for i in range(start, end + 1))
    reg_name = register_name or '"'
    new_regs = registers.set(reg_name, yanked).set_unnamed(yanked, is_delete=False)
    return OperatorResult(buffer=buffer, cursor=cursor, registers=new_regs)


def _delete_or_change(
    op: str,
    buffer: Buffer,
    cursor: Cursor,
    registers: RegisterStore,
    register_name: str | None,
    start: int,
    end: int,
) -> OperatorResult:
    """Delete or change lines, storing deleted text in register."""
    new_buf, deleted = buffer.delete_lines(start, end)
    reg_name = register_name or '"'
    new_regs = registers.set(reg_name, deleted).set_unnamed(deleted, is_delete=True)
    new_row = min(start, new_buf.line_count() - 1)
    new_cursor = cursor.move_to(max(0, new_row), 0)
    return OperatorResult(
        buffer=new_buf,
        cursor=new_cursor,
        registers=new_regs,
        enter_insert=(op == "c"),
    )


def put_lines(
    buffer: Buffer,
    cursor: Cursor,
    registers: RegisterStore,
    register_name: str | None = None,
    above: bool = False,
) -> tuple[Buffer, Cursor]:
    """p/P -- paste from register below/above cursor."""
    reg = registers.get(register_name or '"')
    if not reg.content:
        return buffer, cursor
    insert_at = cursor.row if above else cursor.row + 1
    new_buf = buffer
    for i, line in enumerate(reg.content):
        new_buf = new_buf.insert_line(insert_at + i, line)
    new_cursor = cursor.move_to(insert_at, 0)
    return new_buf, new_cursor


def increment_quantity(buffer: Buffer, cursor: Cursor, count: int = 1) -> Buffer:
    """+ key: increment quantity of card at cursor line (10+ adds 10).

    Preserves the SB:/CMD: prefix and any inline tags.
    """
    if not buffer.is_card_line(cursor.row):
        return buffer
    qty = buffer.quantity_at(cursor.row)
    if qty is None:
        return buffer
    return buffer.set_quantity(cursor.row, qty + count)


def decrement_quantity(
    buffer: Buffer, cursor: Cursor, count: int = 1
) -> tuple[Buffer, Cursor]:
    """- key: decrement (3- subtracts 3). Delete line if qty reaches 0.

    Preserves the SB:/CMD: prefix and any inline tags.
    """
    if not buffer.is_card_line(cursor.row):
        return buffer, cursor
    qty = buffer.quantity_at(cursor.row)
    if qty is None:
        return buffer, cursor
    if qty <= count:
        new_buf, _ = buffer.delete_lines(cursor.row, cursor.row)
        new_row = min(cursor.row, new_buf.line_count() - 1)
        return new_buf, cursor.move_to(max(0, new_row), 0)
    return buffer.set_quantity(cursor.row, qty - count), cursor


# ── Zone moves (ms/mm/md) ────────────────────────────────────────────

ZONE_LABELS = {
    LineType.COMMANDER_ENTRY: "commander",
    LineType.COMPANION_ENTRY: "companion",
    LineType.CARD_ENTRY: "main deck",
    LineType.SIDEBOARD_ENTRY: "sideboard",
    LineType.MAYBEBOARD_ENTRY: "maybeboard",
}
_ZONE_PREFIXES = {
    LineType.COMMANDER_ENTRY: "CMD: ",
    LineType.COMPANION_ENTRY: "CMP: ",
    LineType.CARD_ENTRY: "",
    LineType.SIDEBOARD_ENTRY: "SB: ",
    LineType.MAYBEBOARD_ENTRY: "MB: ",
}
# Zone → its Python-style block header tag ('DCK:', 'CMD:', ...)
_ZONE_TAGS = {
    LineType.CARD_ENTRY: "DCK",
    LineType.COMMANDER_ENTRY: "CMD",
    LineType.COMPANION_ENTRY: "CMP",
    LineType.SIDEBOARD_ENTRY: "SB",
    LineType.MAYBEBOARD_ENTRY: "MB",
}
_BLOCK_INDENT = "    "
# Zones whose blocks come after this zone in the canonical file layout
# (commander, companion, main deck, sideboard, maybeboard).
_ZONE_SUCCESSORS = {
    LineType.COMMANDER_ENTRY: (
        LineType.COMPANION_ENTRY, LineType.CARD_ENTRY,
        LineType.SIDEBOARD_ENTRY, LineType.MAYBEBOARD_ENTRY,
    ),
    LineType.COMPANION_ENTRY: (
        LineType.CARD_ENTRY,
        LineType.SIDEBOARD_ENTRY, LineType.MAYBEBOARD_ENTRY,
    ),
    LineType.CARD_ENTRY: (LineType.SIDEBOARD_ENTRY, LineType.MAYBEBOARD_ENTRY),
    LineType.SIDEBOARD_ENTRY: (LineType.MAYBEBOARD_ENTRY,),
    LineType.MAYBEBOARD_ENTRY: (),
}


@dataclass(frozen=True)
class ZoneMoveResult:
    buffer: Buffer
    cursor: Cursor
    message: str
    moved: bool = False
    # Structural changes, for mark adjustment: row removed from the old
    # buffer, row added in the new buffer (None when only quantities changed).
    deleted_row: int | None = None
    inserted_row: int | None = None
    # Lines added at inserted_row (2 when a new zone block was opened)
    inserted_count: int = 1


def _find_zone_entry(
    buffer: Buffer, name: str, zone: LineType, exclude: int
) -> int | None:
    """Find another line holding `name` in `zone`, or None."""
    for i in range(buffer.line_count()):
        if i == exclude:
            continue
        if buffer.get_line(i).line_type == zone and buffer.card_name_at(i) == name:
            return i
    return None


def _zone_insert_row(buffer: Buffer, zone: LineType) -> int:
    """Row where a new `zone` line belongs: after the zone's last entry,
    else right under the zone's own block header ('DCK:', 'CMD:', ...)
    when one exists, else before the first later-zone block (and its
    blank separator), else at the end of the buffer."""
    last = None
    for i in range(buffer.line_count()):
        if buffer.get_line(i).line_type == zone:
            last = i
    if last is not None:
        return last + 1
    for i in range(buffer.line_count()):
        if parse_zone_header(buffer.get_line(i).text) == _ZONE_TAGS[zone]:
            return i + 1
    for i in range(buffer.line_count()):
        if buffer.get_line(i).line_type in _ZONE_SUCCESSORS[zone]:
            # Step back over the block's own header and separator so the
            # new zone line lands before the block, not inside it.
            while i > 0 and buffer.get_line(i - 1).line_type in (
                LineType.BLANK, LineType.SECTION_HEADER,
            ):
                i -= 1
            return i
    return buffer.line_count()


def _insert_zone_line(
    buffer: Buffer, zone: LineType, body: str
) -> tuple[Buffer, int, int]:
    """Insert a new zone line ('body' = 'N Name…' without prefix) into
    its zone block. Returns (buffer, card_row, lines_inserted).

    A zone with no lines and no block header yet opens as a Python-style
    block — 'CMD:' with the card indented beneath it. Inside an existing
    block the line is written indented to match; next to prefix-style
    entries it gets the SB:/CMD: prefix.
    """
    tag = _ZONE_TAGS[zone]
    has_entries = any(
        buffer.get_line(i).line_type == zone
        for i in range(buffer.line_count())
    )
    has_header = any(
        parse_zone_header(buffer.get_line(i).text) == tag
        for i in range(buffer.line_count())
    )
    row = _zone_insert_row(buffer, zone)
    if row == buffer.line_count() and row > 0:
        prev_type = buffer.get_line(row - 1).line_type
        if prev_type not in (LineType.BLANK, zone):
            buffer = buffer.insert_line(row, "")
            row += 1
    if not has_entries and not has_header:
        buffer = buffer.insert_line(row, f"{tag}:")
        buffer = buffer.insert_line(row + 1, f"{_BLOCK_INDENT}{body}")
        return buffer, row + 1, 2
    text = _zone_line_text(buffer, row, zone, body)
    return buffer.insert_line(row, text), row, 1


def _zone_line_text(buffer: Buffer, row: int, zone: LineType, body: str) -> str:
    """Prefix or indent `body` to match the insertion point's style."""
    if row > 0:
        prev = buffer.get_line(row - 1)
        in_block = parse_zone_header(prev.text) == _ZONE_TAGS[zone] or (
            prev.line_type == zone
            and prev.text[:1].isspace()
            and CARD_PATTERN.match(prev.text) is not None
        )
        if in_block:
            return f"{_BLOCK_INDENT}{body}"
    return f"{_ZONE_PREFIXES[zone]}{body}"


def move_to_zone(
    buffer: Buffer, cursor: Cursor, target: LineType, count: int = 0
) -> ZoneMoveResult:
    """ms/mm/md — move the card at the cursor to another zone.

    count == 0 (no count given) moves every copy; 0 < count < quantity
    splits the entry, leaving the remainder behind. If the target zone
    already holds the card, quantities merge and tags union.
    """
    row = cursor.row
    if not buffer.is_card_line(row):
        return ZoneMoveResult(buffer, cursor, "E: Not on a card line")
    if target not in ZONE_LABELS:
        return ZoneMoveResult(buffer, cursor, "E: Unknown zone")
    src_type = buffer.get_line(row).line_type
    label = ZONE_LABELS[target]
    if src_type == target:
        return ZoneMoveResult(buffer, cursor, f"Already in {label}")

    qty = buffer.quantity_at(row)
    name = buffer.card_name_at(row)
    if qty is None or name is None:
        return ZoneMoveResult(buffer, cursor, "E: Not on a card line")
    moved = qty if count <= 0 else min(count, qty)
    remainder = qty - moved
    tags = buffer.tags_at(row)
    comment = buffer.comment_at(row)

    new_buf = buffer
    deleted_row: int | None = None
    inserted_row: int | None = None
    inserted_count = 1
    merge_row = _find_zone_entry(new_buf, name, target, exclude=row)
    if merge_row is not None:
        existing_qty = new_buf.quantity_at(merge_row) or 0
        new_buf = new_buf.set_quantity(merge_row, existing_qty + moved)
        if tags:
            new_buf = new_buf.set_tags(
                merge_row, new_buf.tags_at(merge_row) | tags
            )
        if remainder > 0:
            new_buf = new_buf.set_quantity(row, remainder)
            dest_row = merge_row
        else:
            new_buf, _ = new_buf.delete_lines(row, row)
            deleted_row = row
            dest_row = merge_row if merge_row < row else merge_row - 1
    else:
        suffix = format_inline_tags(tags) + format_inline_comment(comment)
        body = f"{moved} {name}{suffix}"
        if remainder > 0:
            new_buf = new_buf.set_quantity(row, remainder)
        else:
            new_buf, _ = new_buf.delete_lines(row, row)
            deleted_row = row
        new_buf, dest_row, inserted_count = _insert_zone_line(
            new_buf, target, body
        )
        inserted_row = dest_row

    new_cursor = cursor.move_to(
        max(0, min(dest_row, new_buf.line_count() - 1)), 0
    )
    message = f"Moved {moved}x {name} to {label}"
    if remainder > 0:
        message += f" ({remainder} remain)"
    return ZoneMoveResult(
        new_buf, new_cursor, message, moved=True,
        deleted_row=deleted_row, inserted_row=inserted_row,
        inserted_count=inserted_count,
    )

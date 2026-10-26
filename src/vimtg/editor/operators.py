"""Pure-function vim-style operators for editing a deck buffer.

Supports d/y/c (delete/yank/change) with motions, p/P (put),
and +/- (increment/decrement card quantity).

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vimtg.domain.categories import format_inline_category
from vimtg.domain.deck_lines import (
    MAX_QUANTITY,
    format_inline_comment,
    is_bare_card_line,
    parse_zone_header,
    zone_running_context,
)
from vimtg.domain.tags import format_inline_tags
from vimtg.editor.buffer import HEADER_LINE_TYPES, ZONE_TAG_TYPES, Buffer, LineType
from vimtg.editor.cursor import Cursor

if TYPE_CHECKING:
    from vimtg.editor.placement import PlacementPolicy
from vimtg.editor.motions import (
    HALF_PAGE_MOTIONS,
    MOTION_REGISTRY,
    motion_goto_line,
    motion_last_line,
)
from vimtg.editor.registers import BLACK_HOLE, RegisterStore


@dataclass(frozen=True)
class OperatorResult:
    buffer: Buffer
    cursor: Cursor
    registers: RegisterStore
    enter_insert: bool = False


# How each operator target behaves, vim-style. Exclusive motions stop
# short of the line they land on (dw deletes this card, not the next one
# too; d} stops at the end of the section). Linewise motions include the
# target line. j/k are linewise too but count raw lines (see below).
EXCLUSIVE_MOTIONS = frozenset({"w", "b", "{", "}", "[[", "]]"})
LINEWISE_MOTIONS = frozenset({"j", "k", "G", "gg", "ctrl_d", "ctrl_u"})


def _is_entry(buffer: Buffer, row: int) -> bool:
    """A card line or a sideboard-plan entry — what an operator's
    exclusive range is about."""
    return 0 <= row < buffer.line_count() and (
        buffer.is_card_line(row)
        or buffer.get_line(row).line_type == LineType.PLAN_ENTRY
    )


def _trim_end(buffer: Buffer, start: int, end: int) -> int:
    """Pull `end` back over trailing non-entry lines (blanks, the next
    section's header) so an exclusive range never eats a boundary."""
    while end > start and not _is_entry(buffer, end):
        end -= 1
    return end


def _range_w(buffer: Buffer, row: int, count: int) -> tuple[int, int]:
    """dw: this card through the line before the count-th next card.
    With fewer cards left, through the last one (vim's dw on the last
    word of a line)."""
    pos = row
    moved = 0
    for _ in range(count):
        nxt = buffer.next_card_line(pos)
        if nxt is None:
            break
        pos = nxt
        moved += 1
    if moved == count:
        return row, _trim_end(buffer, row, pos - 1)
    return row, pos


def _range_b(buffer: Buffer, row: int, count: int) -> tuple[int, int]:
    """db: the count previous cards, not the one under the cursor."""
    pos = row
    for _ in range(count):
        prev = buffer.prev_card_line(pos)
        if prev is None:
            break
        pos = prev
    if pos == row:
        return row, row - 1  # nothing before the cursor: empty
    return pos, _trim_end(buffer, pos, row - 1)


def _range_section_forward(buffer: Buffer, row: int, count: int) -> tuple[int, int]:
    """d}: from the cursor to the end of the section (count sections);
    the blank and the next section's header stay."""
    last = buffer.line_count() - 1
    pos = row
    for i in range(count):
        if i > 0 or not _is_entry(buffer, pos):
            nxt = pos + 1
            while nxt <= last and not _is_entry(buffer, nxt):
                nxt += 1
            if nxt > last:
                break
            pos = nxt
        while pos < last and _is_entry(buffer, pos + 1):
            pos += 1
    return row, max(row, pos)


def _range_section_backward(buffer: Buffer, row: int, count: int) -> tuple[int, int]:
    """d{: the cards above the cursor in its section (count sections);
    the cursor line itself is not included, as in vim."""
    pos = row
    for i in range(count):
        if i == 0 and _is_entry(buffer, pos) and _is_entry(buffer, pos - 1):
            pass  # mid-section: back to this section's first card
        else:
            prev = pos - 1
            while prev >= 0 and not _is_entry(buffer, prev):
                prev -= 1
            if prev < 0:
                break
            pos = prev
        while _is_entry(buffer, pos - 1):
            pos -= 1
    if pos >= row:
        return row, row - 1
    return pos, _trim_end(buffer, pos, row - 1)


def _range_header_forward(buffer: Buffer, row: int, count: int) -> tuple[int, int]:
    """d]]: up to, not including, the count-th next header."""
    target = MOTION_REGISTRY["]]"](Cursor(row=row), buffer, count).row
    if target > row and buffer.get_line(target).line_type in HEADER_LINE_TYPES:
        return row, _trim_end(buffer, row, target - 1)
    return row, max(row, target)


def _range_header_backward(buffer: Buffer, row: int, count: int) -> tuple[int, int]:
    """d[[: from the count-th previous header to the line above the cursor."""
    target = MOTION_REGISTRY["[["](Cursor(row=row), buffer, count).row
    if target >= row:
        return row, row - 1
    return target, row - 1


_EXCLUSIVE_RANGES = {
    "w": _range_w,
    "b": _range_b,
    "}": _range_section_forward,
    "{": _range_section_backward,
    "]]": _range_header_forward,
    "[[": _range_header_backward,
}


def resolve_line_range(
    op: str, motion: str | None, cursor: Cursor, buffer: Buffer, count: int
) -> tuple[int, int]:
    """Resolve operator+motion to a line range (start, end inclusive).

    dd/yy/cc (motion=None) -> (cursor.row, cursor.row + count - 1)
    Linewise motions (j k G gg Ctrl-D/U) include the target line;
    exclusive ones (w b { } [[ ]]) stop short of it — see
    EXCLUSIVE_MOTIONS. An empty range comes back with end < start
    (db on the first card): there is nothing to operate on.

    `count` 0 means no count was typed — it only matters for G, where
    dG runs to the end but d8G stops at line 8.
    """
    if motion == "G":
        if count >= 1:
            target = motion_goto_line(cursor, buffer, count)
        else:
            target = motion_last_line(cursor, buffer)
        return (min(cursor.row, target.row), max(cursor.row, target.row))
    count = max(1, count)
    if motion is None:  # doubled operator: dd, yy, cc
        end = min(cursor.row + count - 1, buffer.line_count() - 1)
        return (cursor.row, end)
    # j/k operate on raw lines (vim: dj = exactly two lines). The
    # cursor motions skip blanks, which would silently widen the range
    # across a blank onto the next section or zone-block header.
    # A motion that cannot move at all fails, as in vim: dj or d<C-d>
    # on the last line (dk or d<C-u> on the first) deletes nothing, not
    # the line itself.
    if motion == "j":
        if cursor.row >= buffer.line_count() - 1:
            return (cursor.row, cursor.row - 1)
        return (cursor.row, min(cursor.row + count, buffer.line_count() - 1))
    if motion == "k":
        if cursor.row <= 0:
            return (cursor.row, cursor.row - 1)
        return (max(cursor.row - count, 0), cursor.row)
    exclusive = _EXCLUSIVE_RANGES.get(motion)
    if exclusive is not None:
        return exclusive(buffer, cursor.row, count)
    motion_fn = MOTION_REGISTRY.get(motion)
    if motion_fn is None:
        return (cursor.row, cursor.row)
    target = motion_fn(cursor, buffer, count)
    if motion in HALF_PAGE_MOTIONS and target.row == cursor.row:
        return (cursor.row, cursor.row - 1)
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
    """Execute d/y/c/dd/yy/cc with motion resolution.

    An empty range (db on the first card) changes nothing — except c,
    which still opens the card search, as vim's c with an empty motion
    still enters insert mode.
    """
    # Normalize doubled ops: "dd" -> op="d", motion=None
    actual_op = op[0] if len(op) == 2 else op
    actual_motion = None if len(op) == 2 else motion

    start, end = resolve_line_range(actual_op, actual_motion, cursor, buffer, count)
    start = max(0, start)
    end = min(end, buffer.line_count() - 1)
    if end < start:
        return OperatorResult(
            buffer=buffer, cursor=cursor, registers=registers,
            enter_insert=(actual_op == "c"),
        )

    if actual_op == "y":
        return _yank(buffer, cursor, registers, register_name, start, end)

    if actual_op in ("d", "c"):
        return _delete_or_change(
            actual_op, buffer, cursor, registers, register_name, start, end
        )

    return OperatorResult(buffer=buffer, cursor=cursor, registers=registers)


def store_lines(
    registers: RegisterStore,
    register_name: str | None,
    lines: tuple[str, ...],
    *,
    is_delete: bool,
) -> RegisterStore:
    """File yanked/deleted lines vim-style: into the named register and
    the unnamed one, plus the "1-"9 delete history for a delete. "0 holds
    only the last yank made without a register name. The black hole
    register "_ swallows them and leaves every register untouched."""
    if register_name == BLACK_HOLE:
        return registers
    reg_name = register_name or '"'
    stored = registers.set(reg_name, lines)
    if is_delete or reg_name == '"':
        return stored.set_unnamed(lines, is_delete=is_delete)
    return stored.set('"', lines)


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
    new_regs = store_lines(registers, register_name, yanked, is_delete=False)
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
    new_regs = store_lines(registers, register_name, deleted, is_delete=True)
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
    count: int = 1,
) -> tuple[Buffer, Cursor]:
    """p/P -- paste from register below/above cursor, `count` copies
    as one block; the cursor lands on the first pasted row."""
    reg = registers.get(register_name or '"')
    if not reg.content or count <= 0:
        return buffer, cursor
    insert_at = cursor.row if above else cursor.row + 1
    new_buf = buffer.insert_lines(insert_at, tuple(reg.content) * count)
    return new_buf, cursor.move_to(insert_at, 0)


def increment_quantity(buffer: Buffer, cursor: Cursor, count: int = 1) -> Buffer:
    """+ key: increment quantity of card at cursor line (10+ adds 10).

    Preserves the SB:/CMD: prefix (or a plan entry's sign) and any
    inline tags.
    """
    if not buffer.has_quantity(cursor.row):
        return buffer
    qty = buffer.quantity_at(cursor.row)
    if qty is None:
        return buffer
    # quantity_at clamps what it reads; never write past that
    return buffer.set_quantity(cursor.row, min(qty + count, MAX_QUANTITY))


def decrement_quantity(
    buffer: Buffer, cursor: Cursor, count: int = 1
) -> tuple[Buffer, Cursor]:
    """- key: decrement (3- subtracts 3). Delete line if qty reaches 0.

    Preserves the SB:/CMD: prefix (or a plan entry's sign) and any
    inline tags.
    """
    if not buffer.has_quantity(cursor.row):
        return buffer, cursor
    qty = buffer.quantity_at(cursor.row)
    if qty is None:
        return buffer, cursor
    if qty <= count:
        new_buf, _ = buffer.delete_lines(cursor.row, cursor.row)
        new_row = min(cursor.row, new_buf.line_count() - 1)
        return new_buf, cursor.move_to(max(0, new_row), 0)
    return buffer.set_quantity(cursor.row, qty - count), cursor


# ── Zone moves (zs/zm/zd) ────────────────────────────────────────────

ZONE_LABELS = {
    LineType.COMMANDER_ENTRY: "commander",
    LineType.COMPANION_ENTRY: "companion",
    LineType.CARD_ENTRY: "main deck",
    LineType.SIDEBOARD_ENTRY: "sideboard",
    LineType.MAYBEBOARD_ENTRY: "maybeboard",
}
ZONE_PREFIXES = {
    LineType.COMMANDER_ENTRY: "CMD: ",
    LineType.COMPANION_ENTRY: "CMP: ",
    LineType.CARD_ENTRY: "",
    LineType.SIDEBOARD_ENTRY: "SB: ",
    LineType.MAYBEBOARD_ENTRY: "MB: ",
}
# Zone → its Python-style block header tag ('DCK:', 'CMD:', ...)
# LineType -> its zone tag: the inverse of buffer.ZONE_TAG_TYPES
_ZONE_TAGS = {line_type: tag for tag, line_type in ZONE_TAG_TYPES.items()}
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


# Zones kept alphabetical under auto-sort. Commander/companion order is
# meaningful (partners), and the mainboard sorts by type section instead.
ALPHA_ZONES = frozenset({LineType.SIDEBOARD_ENTRY, LineType.MAYBEBOARD_ENTRY})


def zone_insert_row(
    buffer: Buffer, zone: LineType, sort_name: str | None = None
) -> int:
    """Row where a new `zone` line belongs: alphabetically among the
    zone's entries when `sort_name` is given, else after the zone's
    last entry; else right under the zone's own block header ('DCK:',
    'CMD:', ...) when one exists, else before the first later-zone
    block (and its blank separator), else at the end of the buffer."""
    last = None
    for i in range(buffer.line_count()):
        if buffer.get_line(i).line_type == zone:
            if sort_name is not None:
                existing = buffer.card_name_at(i)
                if existing is not None and existing.lower() > sort_name.lower():
                    return i
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


def insert_zone_line(
    buffer: Buffer, zone: LineType, body: str, sort_name: str | None = None
) -> tuple[Buffer, int, int]:
    """Insert a new zone line ('body' = 'N Name…' without prefix) into
    its zone block. Returns (buffer, card_row, lines_inserted).

    A zone with no lines and no block header yet opens as a Python-style
    block — 'CMD:' with the card indented beneath it. Inside an existing
    block the line is written indented to match; next to prefix-style
    entries it gets the SB:/CMD: prefix. `sort_name` places the line
    alphabetically among the zone's entries.
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
    row = zone_insert_row(buffer, zone, sort_name)
    if row == buffer.line_count() and row > 0:
        prev = buffer.get_line(row - 1)
        if prev.line_type not in (LineType.BLANK, zone) and (
            parse_zone_header(prev.text) != tag
        ):
            buffer = buffer.insert_line(row, "")
            row += 1
    if not has_entries and not has_header:
        buffer = buffer.insert_line(row, f"{tag}:")
        buffer = buffer.insert_line(row + 1, f"{_BLOCK_INDENT}{body}")
        return buffer, row + 1, 2
    text = zone_line_text(buffer, row, zone, body)
    return buffer.insert_line(row, text), row, 1


def zone_line_text(buffer: Buffer, row: int, zone: LineType, body: str) -> str:
    """Prefix or indent `body` to match the insertion point's style.

    Inside the zone's own block the line is bare and indented. Inside a
    FOREIGN open block the explicit prefix is kept but indented — an
    unindented line there would terminate that block and rezone the
    lines after it.
    """
    if row > 0:
        prev = buffer.get_line(row - 1)
        in_own_block = parse_zone_header(prev.text) == _ZONE_TAGS[zone] or (
            prev.line_type == zone
            and prev.text[:1].isspace()
            and is_bare_card_line(prev.text)
        )
        if in_own_block:
            return f"{_BLOCK_INDENT}{body}"
        texts = [buffer.get_line(i).text for i in range(buffer.line_count())]
        if zone_running_context(texts, min(row, len(texts))) is not None:
            return f"{_BLOCK_INDENT}{ZONE_PREFIXES[zone]}{body}"
    return f"{ZONE_PREFIXES[zone]}{body}"


def move_to_zone(
    buffer: Buffer, cursor: Cursor, target: LineType, count: int = 0,
    policy: PlacementPolicy | None = None,
) -> ZoneMoveResult:
    """zs/zm/zd — move the card at the cursor to another zone.

    count == 0 (no count given) moves every copy; 0 < count < quantity
    splits the entry, leaving the remainder behind. If the target zone
    already holds the card, quantities merge and tags union. The card's
    @category token travels with it.

    `policy` (auto-sort on): an md lands where the mainboard placement
    policy says — its type section, its category's section, or the
    uncategorized group (vimtg.editor.placement); a fresh sideboard or
    maybeboard line is placed alphabetically among the zone's entries.
    Without it (or with auto-sort off) lines append after the zone's
    last entry. Commander/companion keep append order — partner order
    matters.
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
    category = buffer.category_at(row)
    alpha = policy.auto_sort if policy is not None else False

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
        suffix = (
            format_inline_category(category)
            + format_inline_tags(tags)
            + format_inline_comment(comment)
        )
        body = f"{moved} {name}{suffix}"
        if remainder > 0:
            new_buf = new_buf.set_quantity(row, remainder)
        else:
            new_buf, _ = new_buf.delete_lines(row, row)
            deleted_row = row
        if target == LineType.CARD_ENTRY and alpha and policy is not None:
            from vimtg.editor.placement import place_mainboard_card

            placed = place_mainboard_card(new_buf, policy, category=category)
            new_buf = placed.buffer.insert_line(
                placed.row, f"{placed.indent}{body}"
            )
            dest_row = placed.row
            # Any new blank + header lines sit just above the card row
            inserted_row = dest_row - placed.lines_added
            inserted_count = placed.lines_added + 1
        else:
            sort_name = name if alpha and target in ALPHA_ZONES else None
            new_buf, dest_row, inserted_count = insert_zone_line(
                new_buf, target, body, sort_name
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

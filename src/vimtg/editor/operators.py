"""Pure-function vim-style operators for editing a deck buffer.

Supports d/y/c (delete/yank/change) with motions, p/P (put),
and +/- (increment/decrement card quantity).

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from vimtg.editor.buffer import Buffer
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


def increment_quantity(buffer: Buffer, cursor: Cursor) -> Buffer:
    """+ key: increment quantity of card at cursor line."""
    if not buffer.is_card_line(cursor.row):
        return buffer
    qty = buffer.quantity_at(cursor.row)
    name = buffer.card_name_at(cursor.row)
    if qty is None or name is None:
        return buffer
    text = buffer.get_line(cursor.row).text.strip()
    if text.startswith("SB:"):
        return buffer.set_line(cursor.row, f"SB: {qty + 1} {name}")
    return buffer.set_line(cursor.row, f"{qty + 1} {name}")


def decrement_quantity(buffer: Buffer, cursor: Cursor) -> tuple[Buffer, Cursor]:
    """- key: decrement. Delete line if qty reaches 0."""
    if not buffer.is_card_line(cursor.row):
        return buffer, cursor
    qty = buffer.quantity_at(cursor.row)
    name = buffer.card_name_at(cursor.row)
    if qty is None or name is None:
        return buffer, cursor
    if qty <= 1:
        new_buf, _ = buffer.delete_lines(cursor.row, cursor.row)
        new_row = min(cursor.row, new_buf.line_count() - 1)
        return new_buf, cursor.move_to(max(0, new_row), 0)
    text = buffer.get_line(cursor.row).text.strip()
    if text.startswith("SB:"):
        return buffer.set_line(cursor.row, f"SB: {qty - 1} {name}"), cursor
    return buffer.set_line(cursor.row, f"{qty - 1} {name}"), cursor

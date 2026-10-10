"""Line-oriented ex commands — TUI-agnostic, zero Textual imports.

The vim ex commands that fit a deck's line model:

    :[range]d [x]       delete lines (into register x)
    :[range]y [x]       yank lines (into register x)
    :[range]m {addr}    move lines below line {addr} (0 = to the top)
    :[range]t {addr}    copy lines below line {addr} (also :co, :copy)
    :undo  :redo        one undo / redo step (also :u, :red)
    :reg [x...]         show register contents (also :registers, :di)
    :marks              show the marks
    :e[!] [file]        edit another deck, or reload this one

A bare range (:12, :$) moves the cursor; the registry handles it.
"""

from __future__ import annotations

from pathlib import Path

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
    resolve_command_range,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.operators import store_lines
from vimtg.editor.registers import RegisterStore, is_clipboard_register

_PREVIEW = 30  # characters of a register/mark line shown in a listing


def _line_range(cmd: ParsedCommand, cursor: Cursor, buffer: Buffer) -> tuple[int, int]:
    """The command's range, clamped to the buffer; the cursor line by default."""
    explicit = resolve_command_range(cmd)
    start, end = explicit if explicit is not None else (cursor.row, cursor.row)
    last = buffer.line_count() - 1
    return max(0, min(start, last)), max(0, min(end, last))


def _address(token: str, cursor: Cursor, buffer: Buffer) -> int | None:
    """A :m / :t destination as the row the lines go BELOW (-1 = above
    the first line); None when it is not an address."""
    token = token.strip()
    if token == ".":
        return cursor.row
    if token == "$":
        return buffer.line_count() - 1
    if token.isdigit():
        return min(int(token), buffer.line_count()) - 1
    return None


def _registers(ctx: EditorContext) -> RegisterStore:
    return ctx.registers if ctx.registers is not None else RegisterStore()


def _register_arg(cmd: ParsedCommand, ctx: EditorContext) -> tuple[str | None, bool]:
    """(register, ok) from :d / :y's argument."""
    arg = cmd.args.strip()
    if not arg:
        return None, True
    if len(arg) == 1 and (arg.isalnum() or arg in '"_+*'):
        return arg, True
    ctx.fail(f"E488: Trailing characters: {arg}")
    return None, False


def _mirror(ctx: EditorContext, register: str | None, lines: tuple[str, ...]) -> None:
    """A "+ / "* register write also goes to the system clipboard (the
    TUI performs the copy from ctx.clipboard_text)."""
    if is_clipboard_register(register):
        ctx.clipboard_text = "\n".join(lines) + "\n"
        ctx.clipboard_label = f"register + ({len(lines)} line{'s' if len(lines) != 1 else ''})"


def cmd_delete(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:[range]d [x] — delete lines into register x (default unnamed)."""
    register, ok = _register_arg(cmd, ctx)
    if not ok:
        return buffer, cursor
    start, end = _line_range(cmd, cursor, buffer)
    new_buf, deleted = buffer.delete_lines(start, end)
    ctx.registers = store_lines(_registers(ctx), register, deleted, is_delete=True)
    _mirror(ctx, register, deleted)
    if ctx.marks is not None:
        ctx.marks = ctx.marks.update_for_delete(start, end)
    ctx.modified = True
    n = end - start + 1
    ctx.message = f"{n} lines deleted" if n > 1 else ""
    row = max(0, min(start, new_buf.line_count() - 1))
    return new_buf, cursor.move_to(row, 0)


def cmd_yank(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:[range]y [x] — yank lines into register x (default unnamed)."""
    register, ok = _register_arg(cmd, ctx)
    if not ok:
        return buffer, cursor
    start, end = _line_range(cmd, cursor, buffer)
    lines = tuple(buffer.get_line(i).text for i in range(start, end + 1))
    ctx.registers = store_lines(_registers(ctx), register, lines, is_delete=False)
    _mirror(ctx, register, lines)
    n = len(lines)
    ctx.message = f"{n} line{'s' if n != 1 else ''} yanked"
    return buffer, cursor


def _move_or_copy(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext, *, move: bool,
) -> tuple[Buffer, Cursor]:
    usage = ":[range]m {address}" if move else ":[range]t {address}"
    dest = _address(cmd.args, cursor, buffer) if cmd.args.strip() else None
    if dest is None:
        ctx.fail(f"E14: Invalid address (usage: {usage})")
        return buffer, cursor
    start, end = _line_range(cmd, cursor, buffer)
    lines = [buffer.get_line(i).text for i in range(start, end + 1)]
    n = len(lines)
    new_buf = buffer
    marks = ctx.marks
    if move:
        if start <= dest < end:
            ctx.fail("E134: Cannot move a range of lines into itself")
            return buffer, cursor
        if dest in (start - 1, end):
            return buffer, cursor.move_to(end, 0)  # already there
        new_buf, _ = new_buf.delete_lines(start, end)
        if marks is not None:
            marks = marks.update_for_delete(start, end)
        if dest > end:
            dest -= n
    insert_at = dest + 1
    for offset, text in enumerate(lines):
        new_buf = new_buf.insert_line(insert_at + offset, text)
    if marks is not None:
        marks = marks.update_for_insert(insert_at, n)
    ctx.marks = marks
    ctx.modified = True
    ctx.message = f"{n} line{'s' if n != 1 else ''} {'moved' if move else 'copied'}"
    return new_buf, cursor.move_to(insert_at + n - 1, 0)


def cmd_move(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:[range]m {address} — move lines below {address} (0 = top)."""
    return _move_or_copy(buffer, cursor, cmd, ctx, move=True)


def cmd_copy(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:[range]t {address} — copy lines below {address} (0 = top)."""
    return _move_or_copy(buffer, cursor, cmd, ctx, move=False)


def cmd_undo(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:undo — one undo step (the session restores the buffer)."""
    ctx.undo_request = "undo"
    return buffer, cursor


def cmd_redo(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:redo — one redo step."""
    ctx.undo_request = "redo"
    return buffer, cursor


def _preview(lines: tuple[str, ...] | str) -> str:
    text = lines if isinstance(lines, str) else (lines[0].strip() if lines else "")
    if len(text) > _PREVIEW:
        text = text[: _PREVIEW - 1] + "…"
    if not isinstance(lines, str) and len(lines) > 1:
        text += f" (+{len(lines) - 1})"
    return text


def cmd_registers(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:reg [names] — list the registers that hold something."""
    registers = _registers(ctx)
    wanted = set(cmd.args.replace(" ", "")) if cmd.args.strip() else None
    shown = [
        f'"{name} {_preview(registers.get(name).content)}'
        for name in registers.names()
        if wanted is None or name in wanted
    ]
    ctx.message = " | ".join(shown) if shown else "No registers set"
    return buffer, cursor


def cmd_marks(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:marks — list the marks with their line number and text."""
    items = ctx.marks.items() if ctx.marks is not None else ()
    shown = []
    for name, mark in items:
        text = buffer.get_line(mark.row).text if mark.row < buffer.line_count() else ""
        shown.append(f"'{name} {mark.row + 1} {_preview(text.strip())}")
    ctx.message = " | ".join(shown) if shown else "No marks set"
    return buffer, cursor


def _edit_target(arg: str, ctx: EditorContext) -> Path | None:
    if not arg:
        return ctx.file_path
    path = Path(arg).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    # 'deck' finds deck.deck, as :w deck writes it
    if not path.exists() and path.suffix != ".deck":
        with_suffix = path.with_name(path.name + ".deck")
        if with_suffix.exists():
            return with_suffix
    return path


def cmd_edit(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:e file — edit another deck (a missing file opens as a new deck);
    :e reloads this deck from disk. Unsaved changes need :e! to drop."""
    target = _edit_target(cmd.args.strip(), ctx)
    if target is None:
        ctx.fail("E32: No file name")
        return buffer, cursor
    if ctx.modified and not cmd.bang:
        ctx.fail("E37: No write since last change (add ! to override)")
        return buffer, cursor
    if target.is_dir():
        ctx.fail(f"E: {target.name} is a directory")
        return buffer, cursor
    if target.exists():
        try:
            target.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            ctx.fail(f"Cannot open {target.name}: {exc}")
            return buffer, cursor
    ctx.edit_path = target
    ctx.discard_requested = cmd.bang and ctx.modified
    return buffer, cursor


def register_line_commands(registry: CommandRegistry) -> None:
    """Register :d :y :m :t/:co :undo :redo :reg :marks :e."""
    registry.register("delete", cmd_delete, aliases=["d"])
    registry.register("yank", cmd_yank, aliases=["y"])
    registry.register("move", cmd_move, aliases=["m"])
    registry.register("copy", cmd_copy, aliases=["t", "co"])
    registry.register("undo", cmd_undo, aliases=["u"])
    registry.register("redo", cmd_redo, aliases=["red"])
    registry.register("registers", cmd_registers, aliases=["reg", "di", "display"])
    registry.register("marks", cmd_marks)
    registry.register("edit", cmd_edit, aliases=["e"])

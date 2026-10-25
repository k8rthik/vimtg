"""Listing and file ex commands — TUI-agnostic, zero Textual imports.

    :reg [x...]         show register contents (also :registers, :di)
    :marks              show the marks
    :e[!] [file]        edit another deck, or reload this one
    :ene[w][!]          edit a new unnamed deck (the new-deck wizard)

Line edits (delete, yank, move, undo) are normal-mode keys: dd, yy, p,
u, Ctrl-R. :g/pat/d and :g/pat/y live in global_cmd. A bare range
(:12, :$) moves the cursor; the registry handles it.
"""

from __future__ import annotations

from pathlib import Path

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    E37,
    CommandRegistry,
    EditorContext,
    NewBuffer,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.registers import RegisterStore

_PREVIEW = 30  # characters of a register/mark line shown in a listing


def _registers(ctx: EditorContext) -> RegisterStore:
    return ctx.registers if ctx.registers is not None else RegisterStore()


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
    if shown:
        ctx.show_listing("Registers", shown, " | ".join(shown))
    else:
        ctx.message = "No registers set"
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
    if shown:
        ctx.show_listing("Marks", shown, " | ".join(shown))
    else:
        ctx.message = "No marks set"
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
        ctx.fail(E37)
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


def cmd_enew(
    buffer: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:enew — edit a new unnamed deck in place of this one (the
    new-deck wizard asks for its name and format). Unsaved changes need
    :enew! to drop."""
    if ctx.modified and not cmd.bang:
        ctx.fail(E37)
        return buffer, cursor
    ctx.new_buffer = NewBuffer()
    ctx.discard_requested = cmd.bang and ctx.modified
    return buffer, cursor


def register_line_commands(registry: CommandRegistry) -> None:
    """Register :reg :marks :e :enew."""
    registry.register("registers", cmd_registers, aliases=["reg", "di", "display"])
    registry.register("marks", cmd_marks)
    registry.register("edit", cmd_edit, aliases=["e"])
    registry.register("enew", cmd_enew, aliases=["ene"])

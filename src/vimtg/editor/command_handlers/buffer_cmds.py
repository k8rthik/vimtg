"""Buffer commands: write, quit, write-quit — TUI-agnostic, zero Textual imports."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor


def cmd_write(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Save deck to file. Sets ctx.message with result."""
    if ctx.file_path is None:
        ctx.message = "No file path set"
        ctx.error = True
        return buffer, cursor
    ctx.modified = False
    ctx.message = f"Written: {ctx.file_path}"
    return buffer, cursor


def cmd_quit(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Quit editor. Fails if buffer modified without bang."""
    if ctx.modified and not cmd.bang:
        ctx.message = "Unsaved changes (use :q! to force)"
        ctx.error = True
        return buffer, cursor
    ctx.quit_requested = True
    ctx.message = ""
    return buffer, cursor


def cmd_write_quit(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Write then quit."""
    if ctx.file_path is None:
        ctx.message = "No file path set"
        ctx.error = True
        return buffer, cursor
    ctx.modified = False
    ctx.quit_requested = True
    ctx.message = f"Written: {ctx.file_path}"
    return buffer, cursor


def register_buffer_commands(registry: CommandRegistry) -> None:
    """Register :w, :q, :wq, :x commands."""
    registry.register("w", cmd_write, aliases=["write"])
    registry.register("q", cmd_quit, aliases=["quit"])
    registry.register("wq", cmd_write_quit)
    registry.register("x", cmd_write_quit)

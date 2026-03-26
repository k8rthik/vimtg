"""Buffer commands: write, quit, write-quit — TUI-agnostic, zero Textual imports."""

from __future__ import annotations

from pathlib import Path

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.slug import generate_unique_path


def _resolve_write_path(cmd: ParsedCommand, ctx: EditorContext) -> Path | None:
    """Determine the target path for a :w command.

    Priority: explicit arg > existing file_path > auto-generated slug.
    """
    if cmd.args:
        name = cmd.args.strip()
        if not name.endswith(".deck"):
            name += ".deck"
        return Path.cwd() / name

    if ctx.file_path is not None:
        return ctx.file_path

    return generate_unique_path(Path.cwd())


def cmd_write(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Save deck to file via ctx.save_fn."""
    if ctx.save_fn is None:
        ctx.message = "Save not available"
        ctx.error = True
        return buffer, cursor

    try:
        target = _resolve_write_path(cmd, ctx)
    except RuntimeError as exc:
        ctx.message = str(exc)
        ctx.error = True
        return buffer, cursor

    try:
        ctx.save_fn(target, buffer.to_text())
    except OSError as exc:
        ctx.message = f"Write failed: {exc}"
        ctx.error = True
        return buffer, cursor

    ctx.file_path = target
    ctx.modified = False
    ctx.message = f"Written: {target.name}"
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
    """Write then quit. Delegates to cmd_write first."""
    buffer, cursor = cmd_write(buffer, cursor, cmd, ctx)
    if not ctx.error:
        ctx.quit_requested = True
    return buffer, cursor


def cmd_home(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Return to greeter screen. Fails if buffer modified without bang."""
    if ctx.modified and not cmd.bang:
        ctx.message = "Unsaved changes (use :home! to force)"
        ctx.error = True
        return buffer, cursor
    ctx.greeter_requested = True
    return buffer, cursor


def register_buffer_commands(registry: CommandRegistry) -> None:
    """Register :w, :q, :wq, :x, :home commands."""
    registry.register("w", cmd_write, aliases=["write"])
    registry.register("q", cmd_quit, aliases=["quit"])
    registry.register("wq", cmd_write_quit)
    registry.register("x", cmd_write_quit)
    registry.register("home", cmd_home, aliases=["greeter"])

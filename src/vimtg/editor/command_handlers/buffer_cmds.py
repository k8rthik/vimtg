"""Buffer commands: write, quit, write-quit — TUI-agnostic, zero Textual imports."""

from __future__ import annotations

from pathlib import Path

from vimtg.data.file_io import file_stamp
from vimtg.domain.deck_lines import match_metadata
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.slug import unique_deck_path
from vimtg.services.recovery import discard_recovery, read_recovery


def _deck_name(buffer: Buffer) -> str:
    """The value of the deck's first '// Deck:' line ('' when unnamed)."""
    for i in range(buffer.line_count()):
        meta = match_metadata(buffer.get_line(i).text)
        if meta is not None and meta[0].lower() == "deck":
            return meta[1].strip()
    return ""


def _resolve_write_path(
    cmd: ParsedCommand, ctx: EditorContext, buffer: Buffer
) -> Path:
    """Determine the target path for a :w command.

    Priority: explicit arg > existing file_path > a file named after the
    deck's '// Deck:' name (slugified, never an existing file) > a
    random MTG-themed slug when the deck is unnamed.
    An explicit name expands ~ and resolves relative to the working
    directory, gaining a .deck suffix when it has none.
    """
    if cmd.args:
        name = cmd.args.strip()
        if not name.endswith(".deck"):
            name += ".deck"
        return Path.cwd() / Path(name).expanduser()

    if ctx.file_path is not None:
        return ctx.file_path

    return unique_deck_path(Path.cwd(), _deck_name(buffer))


def _same_file(a: Path, b: Path | None) -> bool:
    return b is not None and a.resolve() == b.resolve()


def _write_conflict(target: Path, ctx: EditorContext) -> str | None:
    """Why writing `target` without ! could destroy data, or None.

    Writing to another existing file is vim's E13. Writing back to the
    deck's own file is refused when the file changed on disk since it
    was read (another editor, a sync tool, a git checkout).
    """
    if not _same_file(target, ctx.file_path):
        if target.exists():
            return f"E13: File exists: {target.name} (add ! to override)"
        return None
    if ctx.disk_stamp is not None and file_stamp(target) != ctx.disk_stamp:
        return (
            f"{target.name} changed on disk since it was read "
            "(add ! to override)"
        )
    return None


def cmd_write(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Save deck to file via ctx.save_fn.

    `:w name` writes to `name` and makes it the deck's file from then
    on (vim's :saveas). Overwriting another existing file, or a file
    that changed on disk since it was read, needs `:w!`.
    """
    if ctx.save_fn is None:
        ctx.fail("Save not available")
        return buffer, cursor

    try:
        target = _resolve_write_path(cmd, ctx, buffer)
    except RuntimeError as exc:
        ctx.fail(str(exc))
        return buffer, cursor

    if not cmd.bang:
        conflict = _write_conflict(target, ctx)
        if conflict is not None:
            ctx.fail(conflict)
            return buffer, cursor

    try:
        ctx.save_fn(target, buffer.to_text())
    except OSError as exc:
        ctx.fail(f"Write failed: {exc}")
        return buffer, cursor

    ctx.file_path = target
    ctx.disk_stamp = file_stamp(target)
    ctx.file_saved = True
    ctx.modified = False
    ctx.message = f"Written: {target.name}"
    return buffer, cursor


def cmd_quit(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Quit editor. Fails if buffer modified without bang (configurable)."""
    if ctx.modified and not cmd.bang and _confirm_quit_enabled(ctx):
        ctx.fail("Unsaved changes (use :q! to force)")
        return buffer, cursor
    ctx.quit_requested = True
    ctx.message = ""
    return buffer, cursor


def _confirm_quit_enabled(ctx: EditorContext) -> bool:
    """Honor the confirm_quit setting; default to safe (True)."""
    return bool(getattr(ctx.settings, "confirm_quit", True))


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
    if ctx.modified and not cmd.bang and _confirm_quit_enabled(ctx):
        ctx.fail("Unsaved changes (use :home! to force)")
        return buffer, cursor
    ctx.greeter_requested = True
    return buffer, cursor


def cmd_recover(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Load the crash-recovery copy of this deck (:recover! discards it).

    The recovered text replaces the buffer as one undoable, unsaved
    change; the copy itself is removed by the next successful :w.
    """
    if cmd.bang:
        discard_recovery(ctx.file_path)
        ctx.message = "Recovery file discarded"
        return buffer, cursor
    text = read_recovery(ctx.file_path)
    if text is None:
        ctx.fail("No recovery file for this deck")
        return buffer, cursor
    recovered = Buffer.from_text(text)
    ctx.modified = True
    ctx.message = "Recovered unsaved changes (:w to keep, u to undo)"
    return recovered, cursor.clamp(max(0, recovered.line_count() - 1))


def register_buffer_commands(registry: CommandRegistry) -> None:
    """Register :w, :q, :wq, :x, :home commands."""
    registry.register("w", cmd_write, aliases=["write"])
    registry.register("q", cmd_quit, aliases=["quit"])
    registry.register("wq", cmd_write_quit)
    registry.register("x", cmd_write_quit)
    registry.register("home", cmd_home, aliases=["greeter"])
    registry.register("recover", cmd_recover)

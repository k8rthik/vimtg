"""History commands: :checkpoint, :branch — TUI-agnostic, zero Textual imports.

Placeholder commands for history management (checkpoint tagging and branching).
"""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor


def cmd_checkpoint(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:checkpoint "name" — Tag current history state."""
    name = cmd.args.strip().strip('"').strip("'")
    if not name:
        ctx.message = "E: Usage: :checkpoint name"
        ctx.error = True
        return buffer, cursor

    ctx.message = f"Checkpoint: {name}"
    return buffer, cursor


def cmd_branch(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:branch [name] — Create or list branches."""
    ctx.message = f"Branch: {cmd.args}" if cmd.args else "Branches: main"
    return buffer, cursor


def register_history_commands(registry: CommandRegistry) -> None:
    """Register :checkpoint, :cp, and :branch commands."""
    registry.register("checkpoint", cmd_checkpoint, aliases=["cp"])
    registry.register("branch", cmd_branch)

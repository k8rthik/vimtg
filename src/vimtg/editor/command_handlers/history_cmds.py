"""History commands: :history, :commit, :checkpoint.

TUI-agnostic. Handlers have no VCS service handle — they set request
fields on EditorContext that MainScreen interprets (the same pattern as
vcs_commit_description), because the VersionControlService lives on the
screen, not in the editor layer.
"""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor


def cmd_history(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:history / :log — Open the VCS history screen."""
    ctx.open_history_screen = True
    return buffer, cursor


def cmd_commit(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:commit "description" — Create a VCS snapshot of the current deck state."""
    description = cmd.args.strip().strip('"').strip("'")
    if not description:
        ctx.fail("Usage: :commit description")
        return buffer, cursor

    ctx.vcs_commit_description = description
    return buffer, cursor


def cmd_checkpoint(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:checkpoint name — Commit the current deck state and tag it."""
    name = cmd.args.strip().strip('"').strip("'")
    if not name:
        ctx.fail("Usage: :checkpoint name")
        return buffer, cursor

    ctx.vcs_checkpoint_name = name
    return buffer, cursor


def register_history_commands(registry: CommandRegistry) -> None:
    """Register :history, :log, :commit, :checkpoint."""
    registry.register("history", cmd_history, aliases=["log", "hist"])
    registry.register("commit", cmd_commit, aliases=["ci"])
    registry.register("checkpoint", cmd_checkpoint, aliases=["cp"])

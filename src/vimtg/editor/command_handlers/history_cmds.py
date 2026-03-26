"""History commands: :history, :commit, :checkpoint, :branch — TUI-agnostic.

Wires the ex commands to VCS context flags that the MainScreen interprets.
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
        ctx.message = "E: Usage: :commit description"
        ctx.error = True
        return buffer, cursor

    ctx.vcs_commit_description = description
    return buffer, cursor


def cmd_checkpoint(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:checkpoint "name" — Tag current history state (alias for :commit)."""
    name = cmd.args.strip().strip('"').strip("'")
    if not name:
        ctx.message = "E: Usage: :checkpoint name"
        ctx.error = True
        return buffer, cursor

    ctx.vcs_commit_description = name
    return buffer, cursor


def cmd_branch(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:branch — Open history screen to manage branches."""
    ctx.open_history_screen = True
    return buffer, cursor


def register_history_commands(registry: CommandRegistry) -> None:
    """Register :history, :log, :commit, :checkpoint, :branch commands."""
    registry.register("history", cmd_history, aliases=["log", "hist"])
    registry.register("commit", cmd_commit, aliases=["ci"])
    registry.register("checkpoint", cmd_checkpoint, aliases=["cp"])
    registry.register("branch", cmd_branch)

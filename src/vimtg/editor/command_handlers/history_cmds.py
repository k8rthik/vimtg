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
    """:checkpoint name — Tag the current history state with a name."""
    name = cmd.args.strip().strip('"').strip("'")
    if not name:
        ctx.fail("Usage: :checkpoint name")
        return buffer, cursor
    if ctx.history is None:
        ctx.fail("History not available")
        return buffer, cursor

    ctx.history.checkpoint(name)
    ctx.message = f"Checkpoint: {name}"
    return buffer, cursor


def cmd_branch(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:branch — list branches; :branch name — create; :branch! name — switch."""
    if ctx.history is None:
        ctx.fail("History not available")
        return buffer, cursor

    name = cmd.args.strip()

    if not name:
        branches = ctx.history.list_branches()
        if not branches:
            ctx.message = "Branches: (none)"
        else:
            ctx.message = "Branches: " + ", ".join(branches)
        return buffer, cursor

    if cmd.bang:
        restored = ctx.history.switch_branch(name)
        if restored is None:
            ctx.fail(f"Branch not found: {name}")
            return buffer, cursor
        ctx.modified = True
        ctx.message = f"Switched to branch: {name}"
        return restored, cursor

    ctx.history.create_branch(name)
    ctx.message = f"Branch created: {name}"
    return buffer, cursor


def register_history_commands(registry: CommandRegistry) -> None:
    """Register :history, :log, :commit, :checkpoint, :branch commands."""
    registry.register("history", cmd_history, aliases=["log", "hist"])
    registry.register("commit", cmd_commit, aliases=["ci"])
    registry.register("checkpoint", cmd_checkpoint, aliases=["cp"])
    registry.register("branch", cmd_branch)

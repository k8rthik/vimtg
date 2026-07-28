"""Help command handler — :help [command]."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.help_text import has_help


def cmd_help(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Open the full-screen help overlay, optionally focused on one command."""
    topic = cmd.args.strip() if cmd.args else None
    if topic is not None and not has_help(topic):
        ctx.fail(f"No help for: {topic}")
        return buffer, cursor
    ctx.open_help_screen = True
    ctx.help_topic = topic
    return buffer, cursor


def register_help_commands(registry: CommandRegistry) -> None:
    """Register :help and :h commands."""
    registry.register("help", cmd_help, aliases=["h"])

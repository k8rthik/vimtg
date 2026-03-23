"""Help command handler — :help [command]."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.help_text import get_help


def cmd_help(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Display help overview or help for a specific command."""
    topic = cmd.args.strip() if cmd.args else None
    ctx.message = get_help(topic)
    return buffer, cursor


def register_help_commands(registry: CommandRegistry) -> None:
    """Register :help and :h commands."""
    registry.register("help", cmd_help, aliases=["h"])

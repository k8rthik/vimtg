"""Help command handler — :help [command]."""

from __future__ import annotations

from functools import partial

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
    *,
    registry: CommandRegistry,
) -> tuple[Buffer, Cursor]:
    """Open the full-screen help overlay, optionally focused on one command.

    Topics are keyed by canonical command name, so an alias (:help exp)
    opens its command's topic."""
    typed = cmd.args.strip()
    topic = registry.resolve(typed) if typed else None
    if topic is not None and not has_help(topic):
        ctx.fail(f"No help for: {typed}")
        return buffer, cursor
    ctx.open_help_screen = True
    ctx.help_topic = topic
    return buffer, cursor


def cmd_messages(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:messages shows recent messages and errors; :messages clear empties it."""
    arg = (cmd.args or "").strip()
    if arg not in ("", "clear"):
        ctx.fail(f"Invalid argument: {arg}")
        return buffer, cursor
    ctx.ui_request = "messages_clear" if arg == "clear" else "messages"
    return buffer, cursor


def cmd_tips(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:tips shows the getting-started tips; :tips off|on turns them off/on for good."""
    arg = (cmd.args or "").strip().lower()
    requests = {"": "tips_show", "on": "tips_on", "off": "tips_off"}
    if arg not in requests:
        ctx.fail(f"Invalid argument: {arg} (use :tips, :tips on, :tips off)")
        return buffer, cursor
    ctx.ui_request = requests[arg]
    return buffer, cursor


def register_help_commands(registry: CommandRegistry) -> None:
    """Register :help/:h, :messages/:mes and :tips."""
    registry.register("help", partial(cmd_help, registry=registry), aliases=["h"])
    registry.register("messages", cmd_messages, aliases=["mes"])
    registry.register("tips", cmd_tips)

""":sync — refresh card data from Scryfall. TUI-agnostic, zero Textual imports.

The download runs in the background on the app; the handler only
records the request (the status line shows progress).
"""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import CommandRegistry, EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def cmd_sync(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:sync[!] — download card data (! re-downloads even when cached)."""
    ctx.card_sync = "force" if cmd.bang else "sync"
    return buffer, cursor


def register_sync_commands(registry: CommandRegistry) -> None:
    """Register :sync."""
    registry.register("sync", cmd_sync, takes_args=False)

"""Deck info commands: :stats, :validate — TUI-agnostic, zero Textual imports."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor


def cmd_stats(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Show deck statistics in the message bar."""
    lines = buffer.get_lines()
    card_count = sum(
        1 for bl in lines if bl.line_type == LineType.CARD_ENTRY
    )
    sb_count = sum(
        1 for bl in lines if bl.line_type == LineType.SIDEBOARD_ENTRY
    )
    cmd_count = sum(
        1 for bl in lines if bl.line_type == LineType.COMMANDER_ENTRY
    )
    total = card_count + sb_count + cmd_count
    ctx.message = (
        f"Cards: {total} (main: {card_count}, "
        f"sideboard: {sb_count}, commander: {cmd_count})"
    )
    return buffer, cursor


def cmd_validate(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Run basic validation on the buffer. Reports issues via ctx.message."""
    lines = buffer.get_lines()
    issues: list[str] = []

    card_count = sum(
        1 for bl in lines if bl.line_type == LineType.CARD_ENTRY
    )
    if card_count == 0:
        issues.append("No mainboard cards")

    if not issues:
        ctx.message = "Deck OK"
    else:
        ctx.message = "Issues: " + "; ".join(issues)
        ctx.error = True

    return buffer, cursor


def register_deck_commands(registry: CommandRegistry) -> None:
    """Register :stats and :validate commands."""
    registry.register("stats", cmd_stats)
    registry.register("validate", cmd_validate, aliases=["val"])

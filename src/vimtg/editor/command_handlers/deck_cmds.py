"""Deck info commands: :stats, :validate — TUI-agnostic, zero Textual imports."""

from __future__ import annotations

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.analytics import compute_stats
from vimtg.domain.card_types import PRIMARY_TYPES
from vimtg.domain.validation import validate_deck
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
    resolved = ctx.resolved_cards or {}
    if resolved:
        deck = parse_deck_text(buffer.to_text())
        stats = compute_stats(deck, resolved)
        parts = [f"{stats.total_cards} cards"]
        parts.append(f"Avg CMC {stats.average_cmc:.2f}")
        type_parts = []
        for tname in PRIMARY_TYPES:
            count = stats.type_breakdown.counts.get(tname, 0)
            if count > 0:
                type_parts.append(f"{count} {tname}")
        if type_parts:
            parts.append(", ".join(type_parts))
        if stats.total_price_usd is not None:
            parts.append(f"${stats.total_price_usd:.2f}")
        ctx.message = " | ".join(parts)
    else:
        lines = buffer.get_lines()
        card_count = sum(
            1 for bl in lines if bl.line_type == LineType.CARD_ENTRY
        )
        sb_count = sum(
            1 for bl in lines
            if bl.line_type == LineType.SIDEBOARD_ENTRY
        )
        cmd_count = sum(
            1 for bl in lines
            if bl.line_type == LineType.COMMANDER_ENTRY
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
    """Run deck validation — same rules as `vimtg validate` (CLI)."""
    deck = parse_deck_text(buffer.to_text())
    errors = validate_deck(deck, ctx.resolved_cards or {})

    if not errors:
        ctx.message = "Deck OK"
    else:
        ctx.fail("Issues: " + "; ".join(e.message for e in errors))

    return buffer, cursor


def register_deck_commands(registry: CommandRegistry) -> None:
    """Register :stats and :validate commands."""
    registry.register("stats", cmd_stats)
    registry.register("validate", cmd_validate, aliases=["val"])

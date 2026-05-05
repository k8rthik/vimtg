"""Deck info commands: :stats, :validate — TUI-agnostic, zero Textual imports."""

from __future__ import annotations

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.analytics import compute_stats
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor

_BASIC_LANDS = frozenset({
    "Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
    "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
    "Snow-Covered Mountain", "Snow-Covered Forest",
})

_TYPE_NAMES = (
    "Creature", "Instant", "Sorcery", "Enchantment",
    "Artifact", "Planeswalker", "Land",
)


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
        for tname in _TYPE_NAMES:
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
    """Run comprehensive validation on the buffer."""
    deck = parse_deck_text(buffer.to_text())
    issues: list[str] = []

    for entry in deck.entries:
        if entry.quantity <= 0:
            issues.append(
                f"Invalid quantity {entry.quantity} for {entry.card_name}"
            )

    # 4-of rule on mainboard only (excluding basic lands)
    for entry in deck.mainboard():
        if entry.quantity > 4 and entry.card_name not in _BASIC_LANDS:
            issues.append(f">4 copies of {entry.card_name}")

    main_count = sum(e.quantity for e in deck.mainboard())
    if main_count > 0 and main_count < 60:
        issues.append(f"Mainboard has {main_count} cards (min 60)")

    side_count = sum(e.quantity for e in deck.sideboard())
    if side_count > 15:
        issues.append(f"Sideboard has {side_count} cards (max 15)")

    resolved = ctx.resolved_cards or {}
    if resolved:
        for entry in deck.entries:
            if entry.card_name not in resolved:
                issues.append(f"Card not found: {entry.card_name}")

    if main_count == 0:
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

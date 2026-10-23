"""Deck info commands: :stats, :validate — TUI-agnostic, zero Textual imports."""

from __future__ import annotations

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.analytics import stats_summary
from vimtg.domain.validation import legality_skipped_note, validation_report
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.config_options import currency_symbol_for
from vimtg.editor.cursor import Cursor
from vimtg.editor.lint import effective_format


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
        price_source = getattr(ctx.settings, "price_source", "usd") or "usd"
        ctx.message = stats_summary(
            deck, resolved, price_source, currency_symbol_for(price_source)
        )
    else:
        lines = buffer.get_lines()
        card_count = sum(
            1 for bl in lines if bl.line_type == LineType.CARD_ENTRY
        )
        sb_count = sum(
            1 for bl in lines
            if bl.line_type == LineType.SIDEBOARD_ENTRY
        )
        mb_count = sum(
            1 for bl in lines
            if bl.line_type == LineType.MAYBEBOARD_ENTRY
        )
        cmd_count = sum(
            1 for bl in lines
            if bl.line_type == LineType.COMMANDER_ENTRY
        )
        total = card_count + sb_count + cmd_count
        ctx.message = (
            f"Cards: {total} (main: {card_count}, "
            f"sideboard: {sb_count}, commander: {cmd_count}"
            + (f", maybe: {mb_count}" if mb_count else "")
            + ")"
        )
    return buffer, cursor


def cmd_validate(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Run deck validation — the same report as `vimtg validate` (CLI)."""
    deck = parse_deck_text(buffer.to_text())
    default_fmt = getattr(ctx.settings, "default_format", "") or ""
    fmt = effective_format(deck, default_fmt)
    has_db = bool(ctx.resolved_cards) or (
        ctx.card_repo is not None and ctx.card_repo.count() > 0
    )
    report = validation_report(deck, ctx.resolved_cards or {} if has_db else None, fmt)

    errors = report.problems
    n_err = sum(1 for e in errors if e.level == "error")
    if not errors:
        parts = [f"Deck OK ({fmt})" if fmt else "Deck OK"]
    else:
        # Dedupe repeated messages (a 4-row copy-limit violation reads once)
        found: list[str] = []
        seen: set[tuple[str, str]] = set()
        for e in errors:
            if (e.level, e.message) in seen:
                continue
            seen.add((e.level, e.message))
            tag = "E" if e.level == "error" else "W"
            line_part = f" L{e.line_number}" if e.line_number is not None else ""
            found.append(f"{tag}{line_part}: {e.message}")
        parts = [f"{n_err} errors, {len(errors) - n_err} warnings: " + "; ".join(found)]
    if fmt and not report.legality_checked:
        parts.append(legality_skipped_note("no card database", ":sync"))
    if report.bracket:
        parts.append(report.bracket)
    if n_err:
        ctx.fail(" | ".join(parts))
    else:
        ctx.message = " | ".join(parts)
    return buffer, cursor


def register_deck_commands(registry: CommandRegistry) -> None:
    """Register :stats and :validate commands."""
    registry.register("stats", cmd_stats)
    registry.register("validate", cmd_validate, aliases=["val"])

"""Deck validation command: :validate — TUI-agnostic, zero Textual imports."""

from __future__ import annotations

from vimtg.data.deck_repository import missing_quantity_lines, parse_deck_text
from vimtg.domain.validation import legality_skipped_note, validation_report
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.lint import effective_format


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
    report = validation_report(
        deck, ctx.resolved_cards or {} if has_db else None, fmt,
        missing_quantity_lines(buffer.to_text()),
    )

    errors = report.problems
    n_err = sum(1 for e in errors if e.level == "error")
    found: list[str] = []
    if not errors:
        parts = [f"Deck OK ({fmt})" if fmt else "Deck OK"]
    else:
        # Dedupe repeated messages (a 4-row copy-limit violation reads once)
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
    header = parts[0].partition(": ")[0] if found else parts[0]
    lines = [header, *found, *parts[1:]]
    summary = " | ".join(parts)
    ctx.show_listing(
        f"Validation ({fmt})" if fmt else "Validation", lines,
        f"E: {summary}" if n_err else summary, error=bool(n_err),
    )
    return buffer, cursor


def register_deck_commands(registry: CommandRegistry) -> None:
    """Register the :validate command."""
    registry.register("validate", cmd_validate, aliases=["val"])

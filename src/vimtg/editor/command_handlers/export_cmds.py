"""Export/import commands: :export, :import — TUI-agnostic, zero Textual imports.

Wires to ImportExportService for deck format conversion.
"""

from __future__ import annotations

from pathlib import Path

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.errors import CardsNotFoundWarning
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.services.clipboard import copy_to_clipboard
from vimtg.services.import_export_service import DeckFormat, ImportExportService

_FORMAT_MAP: dict[str, DeckFormat] = {
    "arena": DeckFormat.ARENA,
    "mtga": DeckFormat.ARENA,
    "mtgo": DeckFormat.MTGO,
    "dek": DeckFormat.MTGO_DEK,
    "moxfield": DeckFormat.MOXFIELD,
    "archidekt": DeckFormat.ARCHIDEKT,
    "vimtg": DeckFormat.VIMTG,
}


def cmd_export(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:export <format> [file] — Export deck to another format."""
    parts = cmd.args.strip().split(maxsplit=1)
    if not parts:
        ctx.fail("Usage: :export <arena|mtgo|dek|moxfield|archidekt|vimtg> [file]")
        return buffer, cursor

    fmt_name = parts[0].lower()
    fmt = _FORMAT_MAP.get(fmt_name)
    if fmt is None:
        ctx.fail(f"Unknown format: {fmt_name}. Use arena, mtgo, dek, moxfield, archidekt, or vimtg")
        return buffer, cursor

    deck = parse_deck_text(buffer.to_text())
    resolved = ctx.resolved_cards or {}
    service = ImportExportService(card_repo=ctx.card_repo)
    result = service.export_deck(deck, fmt, resolved=resolved)

    if len(parts) > 1:
        out_path = Path(parts[1])
        try:
            out_path.write_text(result, encoding="utf-8")
            ctx.message = f"Exported {fmt_name} to {out_path}"
        except OSError as exc:
            ctx.fail(f"Write failed: {exc}")
    else:
        # Show first line as preview + total line count
        lines = result.strip().split("\n")
        preview = lines[0][:60] if lines else ""
        ctx.message = f"Exported {fmt_name} ({len(lines)} lines): {preview}..."

    return buffer, cursor


def cmd_import(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:import <file|url> — Import a deck from a file or deck-site URL.

    Files parse synchronously (format auto-detected). A Moxfield,
    Archidekt, or ManaBox URL is fetched asynchronously by the TUI —
    the handler only records the request.
    """
    file_arg = cmd.args.strip()
    if not file_arg:
        ctx.fail("Usage: :import <file|deck-url>")
        return buffer, cursor

    from vimtg.services.deck_sources import is_deck_url

    if is_deck_url(file_arg):
        ctx.import_url = file_arg
        return buffer, cursor

    in_path = Path(file_arg)
    if not in_path.exists():
        ctx.fail(f"File not found: {file_arg}")
        return buffer, cursor

    try:
        text = in_path.read_text(encoding="utf-8")
    except OSError as exc:
        ctx.fail(f"Read failed: {exc}")
        return buffer, cursor

    service = ImportExportService(card_repo=ctx.card_repo)
    deck = service.import_deck(text)
    vimtg_text = service.export_deck(deck, DeckFormat.VIMTG)
    new_buffer = Buffer.from_text(vimtg_text)
    ctx.modified = True
    ctx.message = f"Imported {deck.total_cards()} cards from {in_path.name}"

    resolution = service.resolve_cards(deck)
    if resolution.resolved:
        ctx.resolved_cards = dict(resolution.resolved)
    if resolution.unresolved:
        warning = str(CardsNotFoundWarning(len(resolution.unresolved)))
        first_missing = next(
            (n for n in resolution.unresolved if n in resolution.suggestions), None,
        )
        if first_missing is not None:
            suggestion = resolution.suggestions[first_missing]
            warning += f" (did you mean '{suggestion}' for '{first_missing}'?)"
        ctx.message += f" | {warning}"
    return new_buffer, cursor.clamp(new_buffer.line_count() - 1)


def cmd_clipboard(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:clipboard [format] — Copy deck to system clipboard via OSC52."""
    fmt_name = (cmd.args.strip() or "arena").lower()
    fmt = _FORMAT_MAP.get(fmt_name)
    if fmt is None:
        ctx.message = (
            f"E: Unknown format: {fmt_name}. Use arena, mtgo, dek, moxfield, archidekt, or vimtg"
        )
        ctx.error = True
        return buffer, cursor

    deck = parse_deck_text(buffer.to_text())
    resolved = ctx.resolved_cards or {}
    service = ImportExportService(card_repo=ctx.card_repo)
    text = service.export_deck(deck, fmt, resolved=resolved)

    if copy_to_clipboard(text):
        ctx.message = f"Copied {fmt_name} to clipboard ({len(text.splitlines())} lines)"
    else:
        ctx.fail("Clipboard write failed")
    return buffer, cursor


def register_export_commands(registry: CommandRegistry) -> None:
    """Register :export, :exp, :import, :imp, :clipboard, :clip commands."""
    registry.register("export", cmd_export, aliases=["exp"])
    registry.register("import", cmd_import, aliases=["imp"])
    registry.register("clipboard", cmd_clipboard, aliases=["clip"])

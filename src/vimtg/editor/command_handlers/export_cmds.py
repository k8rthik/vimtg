"""Export/import commands: :export, :import — TUI-agnostic, zero Textual imports.

Wires to ImportExportService for deck format conversion.
"""

from __future__ import annotations

from pathlib import Path

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card_names import CardMap
from vimtg.domain.errors import CardsNotFoundWarning
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.services.clipboard import read_clipboard
from vimtg.services.import_export_service import DeckFormat, ImportExportService

_FORMAT_MAP: dict[str, DeckFormat] = {
    "arena": DeckFormat.ARENA,
    "mtga": DeckFormat.ARENA,
    "mtgo": DeckFormat.MTGO,
    "dek": DeckFormat.MTGO_DEK,
    "moxfield": DeckFormat.MOXFIELD,
    "archidekt": DeckFormat.ARCHIDEKT,
    "vimtg": DeckFormat.VIMTG,
    "guide": DeckFormat.GUIDE,  # sideboard guide (Markdown)
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
        ctx.fail("Usage: :export <arena|mtgo|dek|moxfield|archidekt|vimtg|guide> [file]")
        return buffer, cursor

    fmt_name = parts[0].lower()
    fmt = _FORMAT_MAP.get(fmt_name)
    if fmt is None:
        ctx.fail(
            f"Unknown format: {fmt_name}. "
            "Use arena, mtgo, dek, moxfield, archidekt, vimtg, or guide"
        )
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
    """:import [file|url] — Import a deck from a file, a deck-site URL,
    or (with no argument) the system clipboard.

    Files and clipboard text parse synchronously (format auto-detected).
    A Moxfield, Archidekt, or ManaBox URL — typed or on the clipboard —
    is fetched asynchronously by the TUI; the handler only records the
    request.
    """
    from vimtg.services.deck_sources import is_deck_url

    file_arg = cmd.args.strip()
    if not file_arg:
        clip = read_clipboard()
        if clip is None or not clip.strip():
            ctx.fail(
                "Clipboard is empty or unreadable — paste the decklist into "
                "the editor (normal mode), or :import <file|deck-url>"
            )
            return buffer, cursor
        if is_deck_url(clip.strip()):
            ctx.import_url = clip.strip()
            return buffer, cursor
        # Unlike a file, stray clipboard text must never wipe the deck
        return _import_text(clip, "clipboard", buffer, cursor, ctx, require_cards=True)

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
    return _import_text(text, in_path.name, buffer, cursor, ctx)


def _import_text(
    text: str,
    source: str,
    buffer: Buffer,
    cursor: Cursor,
    ctx: EditorContext,
    *,
    require_cards: bool = False,
) -> tuple[Buffer, Cursor]:
    """Replace the buffer with the deck parsed from `text`."""
    service = ImportExportService(card_repo=ctx.card_repo)
    report = service.import_deck_report(text)
    deck = report.deck
    if require_cards and not deck.entries:
        ctx.fail(f"No cards found in {source}")
        return buffer, cursor
    vimtg_text = service.export_deck(deck, DeckFormat.VIMTG)
    new_buffer = Buffer.from_text(vimtg_text)
    ctx.modified = True
    ctx.message = f"Imported {deck.total_cards()} cards from {source}"
    if report.skipped:
        first = report.skipped[0]
        ctx.message += (
            f" | {len(report.skipped)} line(s) skipped"
            f" (line {first.line_number}: {first.text[:40]})"
        )

    resolution = service.resolve_cards(deck)
    if resolution.resolved:
        ctx.resolved_cards = CardMap(resolution.resolved)
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
    """:clipboard [format] — Copy the deck to the system clipboard.

    The copy itself is the TUI's job (it owns the terminal, and OSC 52
    has to go through it): the handler only renders the text.
    """
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

    ctx.clipboard_text = text
    ctx.clipboard_label = f"{fmt_name} ({len(text.splitlines())} lines)"
    return buffer, cursor


def register_export_commands(registry: CommandRegistry) -> None:
    """Register :export, :exp, :import, :imp, :clipboard, :clip commands."""
    registry.register("export", cmd_export, aliases=["exp"])
    registry.register("import", cmd_import, aliases=["imp"])
    registry.register("clipboard", cmd_clipboard, aliases=["clip"])

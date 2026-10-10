"""Export/import commands: :export, :import — TUI-agnostic, zero Textual imports.

Wires to ImportExportService for deck format conversion.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from vimtg.data.deck_repository import parse_deck_text
from vimtg.data.file_io import atomic_write_text
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
from vimtg.services.import_export_service import (
    NO_FORMAT_NOTE,
    DeckFormat,
    ImportExportService,
    normalize_text,
    structured_deck_text,
)

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


def _export_target(arg: str) -> Path:
    """The file an :export writes: ~ expanded, relative to the cwd."""
    path = Path(arg).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def _export_conflict(target: Path, ctx: EditorContext, bang: bool) -> str | None:
    """Why :export must not write `target`, or None.

    The open deck's own file is never an export target (the buffer
    would stay "unmodified" over a file that no longer holds it, so :q
    would lose the deck without a warning) — not even with !. Any other
    existing file is vim's E13 unless ! is given.
    """
    if ctx.file_path is not None and target.resolve() == ctx.file_path.resolve():
        return (
            f"Cannot export over the open deck {target.name} "
            "(choose another file name; :w saves the deck)"
        )
    if target.exists() and not bang:
        return f"E13: File exists: {target.name} (use :export! to overwrite)"
    return None


def cmd_export(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:export[!] <format> [file] — Export the deck to another format.

    With a file name the export is written there (atomically); an
    existing file needs :export!, and the open deck's own file is
    always refused. Without one the export goes to the clipboard.
    """
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

    if fmt is DeckFormat.VIMTG:
        # vimtg -> vimtg is the buffer itself: re-serializing would drop
        # section headers, block layout and comment positions
        result = buffer.to_text()
    else:
        deck = parse_deck_text(buffer.to_text())
        service = ImportExportService(card_repo=ctx.card_repo)
        result = service.export_deck(deck, fmt, resolved=ctx.resolved_cards or {})

    if len(parts) == 1:
        ctx.clipboard_text = result
        ctx.clipboard_label = f"{fmt_name} export ({len(result.splitlines())} lines)"
        return buffer, cursor

    target = _export_target(parts[1].strip())
    conflict = _export_conflict(target, ctx, cmd.bang)
    if conflict is not None:
        ctx.fail(conflict)
        return buffer, cursor
    try:
        atomic_write_text(target, result)
    except OSError as exc:
        ctx.fail(f"Write failed: {exc}")
        return buffer, cursor
    ctx.message = f"Exported {fmt_name} to {Path(parts[1].strip()).expanduser()}"
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
    return _import_text(text, in_path.name, buffer, cursor, ctx, deck_name=in_path.stem)


def _import_text(
    text: str,
    source: str,
    buffer: Buffer,
    cursor: Cursor,
    ctx: EditorContext,
    *,
    require_cards: bool = False,
    deck_name: str = "",
) -> tuple[Buffer, Cursor]:
    """Replace the buffer with the deck parsed from `text`.

    A vimtg deck comes in verbatim (its layout is the user's). Any other
    format is laid out like a new deck — '// Deck:' / '// Format:' lines
    and CMD:/DCK:/SB: blocks, grouped by type when cards resolve — with
    names normalised to each card's official name. `deck_name` (the
    file's stem) names a deck whose text does not.
    """
    service = ImportExportService(card_repo=ctx.card_repo)
    report = service.import_deck_report(text)
    deck = report.deck
    if require_cards and not deck.entries:
        ctx.fail(f"No cards found in {source}")
        return buffer, cursor
    if deck_name and not deck.metadata.name:
        deck = replace(deck, metadata=replace(deck.metadata, name=deck_name))
    resolution = service.resolve_cards(deck)
    if service.detect_format(text) is DeckFormat.VIMTG:
        vimtg_text = normalize_text(text)
    else:
        vimtg_text = structured_deck_text(deck, resolution.resolved)
    new_buffer = Buffer.from_text(vimtg_text)
    ctx.modified = True
    ctx.message = f"Imported {deck.total_cards()} cards from {source}"
    if report.skipped:
        first = report.skipped[0]
        ctx.message += (
            f" | {len(report.skipped)} line(s) skipped"
            f" (line {first.line_number}: {first.text[:40]})"
        )

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
    if deck.entries and not deck.metadata.format.strip():
        ctx.message += f" | {NO_FORMAT_NOTE}"
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

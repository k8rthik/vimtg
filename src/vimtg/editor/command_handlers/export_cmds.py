"""Export/import commands: :export, :import — TUI-agnostic, zero Textual imports.

Wires to ImportExportService for deck format conversion.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path

from vimtg.data.deck_repository import parse_deck_text
from vimtg.data.file_io import atomic_write_text
from vimtg.domain.card import Card
from vimtg.domain.collection import missing_list, ownership
from vimtg.domain.deck import Deck
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.collection_cmds import NO_COLLECTION
from vimtg.editor.commands import (
    E37,
    CommandRegistry,
    EditorContext,
    NewBuffer,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.services.clipboard import read_clipboard
from vimtg.services.deck_service import saved_text
from vimtg.services.export_targets import (
    DeckFormat,
    ExportIssue,
    ExportTarget,
    IssueLevel,
    check_export,
    exported_card_count,
    target_named,
)
from vimtg.services.import_export_service import (
    PRIMARY_FORMAT_NAMES,
    ImportExportService,
    format_list,
)


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


def _render_export(buffer: Buffer, deck: Deck, target: ExportTarget, ctx: EditorContext) -> str:
    """The deck as `target` takes it, as :export and :clipboard both produce it."""
    if target.fmt is DeckFormat.VIMTG:
        # vimtg -> vimtg is the buffer as :w writes it: re-serializing
        # would drop section headers, block layout and comment positions
        return saved_text(buffer.to_text(), _on_disk(ctx.file_path))
    service = ImportExportService(card_repo=ctx.card_repo)
    return service.export(deck, target, resolved=ctx.resolved_cards or {})


def _card_data(ctx: EditorContext) -> Mapping[str, Card] | None:
    """The deck's resolved cards for export checks, or None when there
    is no card database (none, empty, or unreadable)."""
    if ctx.resolved_cards:
        return ctx.resolved_cards
    try:
        has_cards = ctx.card_repo is not None and ctx.card_repo.count() > 0
    except sqlite3.Error:
        has_cards = False
    return {} if has_cards else None


def _checked(
    buffer: Buffer, target: ExportTarget, bang: bool, ctx: EditorContext
) -> tuple[str, str] | None:
    """Run `target`'s checks and render the export: (text, the note its
    success message ends with), or None when an error blocks it (shown,
    unless ! overrides). Every issue goes to :messages."""
    deck = parse_deck_text(buffer.to_text())
    issues = check_export(deck, _card_data(ctx), target)
    ctx.logged.extend(
        (i.level is IssueLevel.ERROR, f"{target.name}: {i.text(named=None)}") for i in issues
    )
    errors = [i for i in issues if i.level is IssueLevel.ERROR]
    if errors and not bang:
        ctx.fail(f"{errors[0].text()} (:export! {target.name} overrides)")
        return None
    count = f" ({exported_card_count(deck, target)} cards)" if target.counts_cards else ""
    return _render_export(buffer, deck, target, ctx), count + _issue_note(issues)


def _issue_note(issues: tuple[ExportIssue, ...]) -> str:
    """'; 1 error, 2 warnings (see :messages)', or '' with no issues."""
    counts = [
        (sum(i.level is level for i in issues), level.value)
        for level in (IssueLevel.ERROR, IssueLevel.WARNING)
    ]
    parts = [f"{n} {word}{'s' if n > 1 else ''}" for n, word in counts if n]
    return f"; {', '.join(parts)} (see :messages)" if parts else ""


def _on_disk(path: Path | None) -> str | None:
    """The deck file's text as the editor read it, or None without one."""
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
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
    `:export missing` is the shopping list against the loaded
    collection (see :collection), one 'N Card Name' line per card.
    """
    parts = cmd.args.strip().split(maxsplit=1)
    if not parts:
        ctx.fail(f"Usage: :export <{'|'.join(PRIMARY_FORMAT_NAMES)}|missing> [file]")
        return buffer, cursor

    fmt_name = parts[0].lower()
    file_arg = parts[1].strip() if len(parts) > 1 else None
    if fmt_name == "missing":
        if ctx.collection is None:
            ctx.fail(NO_COLLECTION)
            return buffer, cursor
        owns = ownership(parse_deck_text(buffer.to_text()), ctx.collection)
        result = missing_list(owns, ctx.resolved_cards or {})
        if not result:
            ctx.message = "Nothing missing: the collection covers this deck"
            return buffer, cursor
        _deliver_export(result, "missing cards", "missing cards", file_arg, cmd.bang, ctx)
        return buffer, cursor

    target = target_named(fmt_name)
    if target is None:
        ctx.fail(f"Unknown format: {fmt_name}. Use {format_list()}")
        return buffer, cursor

    checked = _checked(buffer, target, cmd.bang, ctx)
    if checked is not None:
        result, note = checked
        _deliver_export(result, fmt_name, f"{fmt_name} export", file_arg, cmd.bang, ctx, note)
    return buffer, cursor


def _deliver_export(
    result: str,
    what: str,
    clipboard_label: str,
    file_arg: str | None,
    bang: bool,
    ctx: EditorContext,
    note: str = "",
) -> None:
    """Hand `result` to the clipboard (no file, labelled `clipboard_label`)
    or write it to `file_arg` ('Exported {what} to ...'); `note` ends
    the success message."""
    if file_arg is None:
        ctx.clipboard_text = result
        ctx.clipboard_label = f"{clipboard_label} ({len(result.splitlines())} lines)"
        ctx.clipboard_note = note
        return
    target = _export_target(file_arg)
    conflict = _export_conflict(target, ctx, bang)
    if conflict is not None:
        ctx.fail(conflict)
        return
    try:
        # The export's own line endings, so a CSV keeps its \r\n and the
        # file matches what :clipboard copies, on every platform
        atomic_write_text(target, result, newline="")
    except OSError as exc:
        ctx.fail(f"Write failed: {exc}")
        return
    ctx.message = f"Exported {what} to {Path(file_arg).expanduser()}{note}"


def cmd_import(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:import[!] [file|url] — Import a deck from a file, a deck-site URL,
    or (with no argument) the system clipboard, into a new unnamed
    buffer in place of the deck (as the greeter's import does), so a
    following :w never overwrites the deck that was open. Unsaved
    changes refuse with E37; ! discards them.

    Files and clipboard text parse synchronously (format auto-detected).
    A deck URL from any site in services.deck_sources, typed or on the
    clipboard, is fetched asynchronously by the TUI; the handler only
    records the request.
    """
    from vimtg.services.deck_sources import is_deck_url

    if ctx.modified and not cmd.bang:
        ctx.fail(E37)
        return buffer, cursor
    ctx.import_force = cmd.bang
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
    """Open the deck parsed from `text` (see ImportExportService.to_vimtg)
    as a new buffer; `deck_name` (the file's stem) names a deck whose
    text does not."""
    result = ImportExportService(card_repo=ctx.card_repo).to_vimtg(text, name=deck_name)
    if require_cards and not result.deck.entries:
        ctx.fail(f"No cards found in {source}")
        return buffer, cursor
    ctx.new_buffer = NewBuffer(text=result.text, message=result.summary(source))
    ctx.discard_requested = ctx.import_force and ctx.modified
    return buffer, cursor


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
    target = target_named(fmt_name)
    if target is None:
        ctx.message = f"E: Unknown format: {fmt_name}. Use {format_list()}"
        ctx.error = True
        return buffer, cursor

    checked = _checked(buffer, target, False, ctx)
    if checked is None:
        return buffer, cursor
    text, ctx.clipboard_note = checked
    ctx.clipboard_text = text
    ctx.clipboard_label = f"{fmt_name} ({len(text.splitlines())} lines)"
    return buffer, cursor


def register_export_commands(registry: CommandRegistry) -> None:
    """Register :export, :exp, :import, :imp, :clipboard, :clip commands."""
    registry.register("export", cmd_export, aliases=["exp"])
    registry.register("import", cmd_import, aliases=["imp"])
    registry.register("clipboard", cmd_clipboard, aliases=["clip"])

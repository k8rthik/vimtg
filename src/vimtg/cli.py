"""CLI entry point for vimtg."""

from __future__ import annotations

import errno
import re
import sqlite3
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
import httpx
from click.shell_completion import CompletionItem

from vimtg import __version__
from vimtg.config.paths import cache_dir, db_path
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.deck_repository import DeckRepository
from vimtg.data.file_io import atomic_write_text
from vimtg.data.scryfall_sync import ScryfallSync, card_data_note, describe_sync_error
from vimtg.services.deck_service import DeckService, editor_line_numbers
from vimtg.services.import_export_service import FORMAT_NAMES, IMPORT_FORMAT_NAMES
from vimtg.services.search_service import TAGS_NOT_SYNCED, SearchService, SearchSyntaxError

if TYPE_CHECKING:
    from vimtg.domain.card import Card
    from vimtg.domain.deck import Deck, DeckEntry
    from vimtg.domain.deck_lines import MissingQuantityLine


def _make_service() -> DeckService:
    return DeckService(deck_repo=DeckRepository())


def _make_card_repo() -> CardRepository:
    db = Database(db_path())
    try:
        db.initialize()
    except sqlite3.Error:
        db.close()  # a corrupt file fails mid-connect; don't leak the handle
        raise
    return CardRepository(db)


def _friendly_error(exc: OSError | UnicodeDecodeError | sqlite3.Error) -> str:
    """A one-line message plus a hint for an ordinary environment error."""
    if isinstance(exc, UnicodeDecodeError):
        return (
            f"cannot read file: it is not UTF-8 text ({exc.reason}).\n"
            "Hint: re-save the deck as UTF-8, or check you passed the right file."
        )
    if isinstance(exc, sqlite3.Error):
        return (
            f"card database error: {exc}\n"
            f"Hint: the database at {db_path()} may be corrupt — run "
            "`vimtg sync` (or start vimtg) to rebuild it; deck history is "
            "salvaged and the damaged file kept as a backup."
        )
    target = exc.filename if exc.filename is not None else ""
    reason = exc.strerror or str(exc)
    hint = {
        errno.ENOENT: "check the path exists (and its parent directory, for output files).",
        errno.EISDIR: "pass a deck file, not a directory.",
        errno.ENOTDIR: "a component of the path is not a directory.",
        errno.EACCES: "check the file and directory permissions.",
        errno.EPERM: "check the file and directory permissions.",
        errno.ENOSPC: "free some disk space and retry.",
    }.get(exc.errno or 0)
    msg = f"{target}: {reason}" if target else reason
    return msg + (f"\nHint: {hint}" if hint else "")


class _DeckFileGroup(click.Group):
    """Vim-style invocation: `vimtg burn.deck` opens the editor.

    A first token that is not a subcommand but is an existing file (or
    ends in .deck — a new deck to be created on :w) opens that deck.
    Anything else still errors as an unknown command.
    """

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            token = args[0]
            if Path(token).is_file() or token.endswith(".deck"):
                return _open_deck.name, _open_deck, args
            raise

    def invoke(self, ctx: click.Context) -> Any:
        """Turn ordinary environment errors into a clean CLI error.

        A bad path, a non-UTF-8 file or a corrupt database is user
        input, not a bug — print one line and a hint, exit non-zero,
        instead of a traceback.
        """
        try:
            return super().invoke(ctx)
        except OSError as exc:
            if exc.errno == errno.EPIPE:  # click handles broken pipes itself
                raise
            raise click.ClickException(_friendly_error(exc)) from exc
        except (UnicodeDecodeError, sqlite3.Error) as exc:
            raise click.ClickException(_friendly_error(exc)) from exc


@click.group(cls=_DeckFileGroup, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="vimtg")
@click.pass_context
def main(ctx: click.Context) -> None:
    """vimtg — Vim-powered MTG deck builder."""
    if ctx.invoked_subcommand is None:
        _launch_editor(None)


def _complete_format(
    ctx: click.Context, param: click.Parameter, incomplete: str,
) -> list[CompletionItem]:
    """Shell completion for --format: the known format names."""
    from vimtg.domain.formats import known_formats

    prefix = incomplete.lower()
    return [CompletionItem(f) for f in known_formats() if f.startswith(prefix)]


@main.command()
@click.argument("name")
@click.option(
    "--format", "-f", "fmt", default="", help="MTG format",
    shell_complete=_complete_format,
)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--force", is_flag=True, help="Overwrite an existing file")
def new(name: str, fmt: str, output: str | None, force: bool) -> None:
    """Create a new deck file (NAME.deck unless -o is given).

    Refuses to overwrite an existing file unless --force is given.
    """
    name = name.strip()
    if name.lower().endswith(".deck"):
        name = name[: -len(".deck")].rstrip()
    if output:
        out_path = Path(output).expanduser()
    else:
        _check_deck_filename(name)
        out_path = Path.cwd() / f"{name}.deck"

    _check_output_path(out_path, force)

    service = _make_service()
    text = service.new_deck(name=name, fmt=fmt)
    service.save_deck(text, out_path)
    click.echo(f"Created {out_path}")


def _check_output_path(out_path: Path, force: bool) -> None:
    """Refuse an -o path that is a directory, or an existing file
    without --force."""
    if out_path.is_dir():
        raise click.ClickException(
            f"{out_path} is a directory (give a file path to -o)"
        )
    if out_path.exists() and not force:
        raise click.ClickException(
            f"{out_path} already exists (use --force to overwrite)"
        )


def _check_deck_filename(name: str) -> None:
    """Reject names that cannot become a plain NAME.deck in the cwd."""
    if not name:
        raise click.BadParameter("deck name must not be empty", param_hint="NAME")
    if any(sep in name for sep in ("/", "\\", "\0")):
        raise click.BadParameter(
            f"{name!r} contains a path separator; use -o PATH to choose "
            "where the file goes",
            param_hint="NAME",
        )
    if name.startswith("."):
        raise click.BadParameter(
            f"{name!r} would create a hidden file", param_hint="NAME",
        )


_NO_CARD_DB = "no card database"
_UNREADABLE_CARD_DB = "card database unreadable, it may be corrupt"


def _open_card_db() -> tuple[Database | None, str]:
    """The synced card database, or (None, why there is none).

    The one place a command decides whether card data is usable: no
    file (or no data directory to look in) and an empty database are
    "no card database"; a file that exists but will not open or lacks
    the card tables is "unreadable", which the user should hear
    instead. The caller closes the database.
    """
    try:
        path = db_path()
    except OSError:  # the data directory cannot be created
        return None, _NO_CARD_DB
    if not path.is_file():
        return None, _NO_CARD_DB
    db = Database(path)
    try:
        db.initialize()
        if CardRepository(db).count() > 0:
            return db, ""
    except sqlite3.Error:
        db.close()
        return None, _UNREADABLE_CARD_DB
    db.close()
    return None, _NO_CARD_DB


def _try_card_repo() -> CardRepository | None:
    """A populated card repository, or None when no usable database exists."""
    db, _note = _open_card_db()
    return CardRepository(db) if db is not None else None


def _no_card_db_note() -> str:
    """Why _try_card_repo found no card data, for a '(… — run vimtg
    sync)' note."""
    db, note = _open_card_db()
    if db is not None:  # it is usable after all; the note is moot
        db.close()
        return _NO_CARD_DB
    return note


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--strict",
    is_flag=True,
    help="Exit non-zero on warnings too (e.g. unknown card names); "
    "requires a card database.",
)
def validate(path: str, strict: bool) -> None:
    """Validate a deck file (format-aware when a card database exists)."""
    from vimtg.config.settings import load_settings
    from vimtg.data.deck_repository import missing_quantity_lines
    from vimtg.domain.validation import legality_skipped_note, validation_report
    from vimtg.editor.lint import effective_format

    card_repo = _try_card_repo()
    service = DeckService(deck_repo=DeckRepository(), card_repo=card_repo)
    file_path = Path(path)
    text, deck = service.open_deck(file_path)

    if strict and card_repo is None:
        click.echo(
            f"{file_path.name}: error: --strict needs a card database to "
            "check card names; run 'vimtg sync'",
            err=True,
        )
        sys.exit(1)
    fmt = effective_format(deck, load_settings().default_format)
    missing = missing_quantity_lines(text)
    report = validation_report(deck, _resolve(card_repo, deck, missing), fmt, missing)

    if fmt and not report.legality_checked:
        skipped = legality_skipped_note(_no_card_db_note(), "'vimtg sync'")
        click.echo(f"({skipped})", err=True)
    if card_repo is not None:
        note = card_data_note(card_repo.count(), card_repo.get_last_sync())
        if note:
            click.echo(note, err=True)

    if not report.problems:
        click.echo(f"{file_path.name}: ok" + (f" ({fmt})" if fmt else ""))
        if report.bracket:
            click.echo(f"{file_path.name}: info: {report.bracket}")
        return

    has_errors = False
    # The file's own line goes in the file:line: slot (what other
    # editors and quickfix lists jump to); when the vimtg editor shows
    # that line elsewhere (it scaffolds missing '// Tags:'-style lines
    # on open), its line number follows the message
    shown_at = editor_line_numbers(text)
    for err in report.problems:
        line_part = f"{err.line_number}:" if err.line_number is not None else ""
        note = ""
        if err.line_number is not None:
            editor_line = shown_at.get(err.line_number, err.line_number)
            if editor_line != err.line_number:
                note = f" (line {editor_line} in the vimtg editor)"
        click.echo(f"{file_path.name}:{line_part} {err.level}: {err.message}{note}")
        if err.level == "error" or strict:
            has_errors = True
    # Informational only: never an error, and --strict ignores it.
    if report.bracket:
        click.echo(f"{file_path.name}: info: {report.bracket}")

    if has_errors:
        sys.exit(1)


@main.command()
@click.argument("path", type=click.Path(exists=True))
def info(path: str) -> None:
    """Show deck summary: name, format, every zone's card count, and
    (with card data) a one-line stats summary."""
    from vimtg.config.settings import load_settings
    from vimtg.data.deck_repository import missing_quantity_lines
    from vimtg.domain.analytics import stats_summary
    from vimtg.domain.validation import missing_quantity_warnings
    from vimtg.editor.config_options import currency_symbol_for

    card_repo = _try_card_repo()
    service = DeckService(deck_repo=DeckRepository(), card_repo=card_repo)
    file_path = Path(path)
    text, deck = service.open_deck(file_path)
    settings = load_settings()
    missing = missing_quantity_lines(text)
    resolved = _resolve(card_repo, deck, missing)

    fmt = deck.metadata.format.strip() or "(none)"
    if not deck.metadata.format.strip() and settings.default_format:
        fmt = f"{settings.default_format} (default_format)"
    rows = [("Deck", deck.metadata.name or "(unnamed)"), ("Format", fmt)]
    for label, entries, always in (
        ("Commander", deck.commanders(), False),
        ("Companion", deck.companions(), False),
        ("Mainboard", deck.mainboard(), True),
        ("Sideboard", deck.sideboard(), True),
        ("Maybeboard", deck.maybeboard(), False),
    ):
        if entries or always:
            rows.append((label, _zone_count(entries)))
    if resolved is not None:
        source = settings.price_source
        rows.append(
            ("Stats", stats_summary(deck, resolved, source, currency_symbol_for(source)))
        )
    for label, value in rows:
        click.echo(f"{label + ':':<12}{value}")
    for warning in missing_quantity_warnings(missing, resolved):
        click.echo(
            f"{file_path.name}:{warning.line_number}: warning: {warning.message}", err=True
        )


def _resolve(
    card_repo: CardRepository | None, deck: Deck, missing: tuple[MissingQuantityLine, ...]
) -> dict[str, Card] | None:
    """The deck's cards (and the cards its quantity-less lines name) by name, or
    None without a card database."""
    if card_repo is None:
        return None
    return card_repo.get_by_names(
        [*deck.unique_card_names(), *(m.card_name for m in missing)]
    )


def _zone_count(entries: tuple[DeckEntry, ...]) -> str:
    """'56 cards (2 unique)' for one zone's entries."""
    total = sum(e.quantity for e in entries)
    unique = len({e.card_name for e in entries})
    return f"{total} card{'' if total == 1 else 's'} ({unique} unique)"


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--markdown", is_flag=True, help="Print the guide as Markdown")
def guide(path: str, markdown: bool) -> None:
    """Print the deck's sideboard plans (VS: blocks)."""
    from vimtg.domain.sideboard_plan import format_guide_markdown

    service = _make_service()
    _text, deck = service.open_deck(Path(path))
    if not deck.plans:
        click.echo("No sideboard plans")
        return
    if markdown:
        click.echo(format_guide_markdown(deck), nl=False)
        return
    for i, plan in enumerate(deck.plans):
        if i:
            click.echo()
        mark = "" if plan.is_balanced else " !"
        click.echo(f"vs {plan.name}  {plan.summary()}{mark}")
        for entry in plan.entries:
            click.echo(f"  {entry.text()}")


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--seed", type=int, default=None, help="Seed the shuffle (repeatable hands)")
@click.option(
    "--draws", type=click.IntRange(min=0), default=0,
    help="Also draw this many cards after the opener",
)
@click.option("--plan", "plan_name", default="", help="Use a sideboard plan's post-board deck")
def hand(path: str, seed: int | None, draws: int, plan_name: str) -> None:
    """Print a sample opening hand and land odds."""
    import random

    from vimtg.config.settings import load_settings
    from vimtg.domain.sample_hand import build_source, deal, format_hand
    from vimtg.domain.sample_hand import draw as draw_card
    from vimtg.domain.sideboard_plan import find_plan

    card_repo = _try_card_repo()
    service = DeckService(deck_repo=DeckRepository(), card_repo=card_repo)
    _text, deck = service.open_deck(Path(path))
    plan = None
    if plan_name:
        plan = find_plan(deck, plan_name)
        if plan is None:
            raise click.ClickException(f"No sideboard plan named {plan_name!r}")
    resolved = service.resolve_cards(deck)[0] if card_repo is not None else None
    fmt = deck.metadata.format or load_settings().default_format
    source = build_source(deck, resolved, fmt, plan)
    if not source.library:
        raise click.ClickException("No cards in the main deck")
    if card_repo is None:
        click.echo(
            f"({_no_card_db_note()} — only basic lands count as lands; "
            "run 'vimtg sync')",
            err=True,
        )
    state = deal(source.library, random.Random(seed), free_mulligan=source.free_mulligan)
    for _ in range(min(draws, len(state.library))):
        state = draw_card(state)
    click.echo(format_hand(source, state, seed), nl=False)


@main.command(name="sync")
@click.option("--force", is_flag=True, help="Force re-download")
def sync_cmd(force: bool) -> None:
    """Download card data from Scryfall."""
    from vimtg.data.db_recovery import open_database

    # A damaged database is backed up and rebuilt (history salvaged)
    # so the sync can repopulate it
    opened = open_database(db_path(), sync_hint="downloading it now")
    if opened.in_memory:
        opened.db.close()
        raise click.ClickException(opened.reason or opened.warning)
    if opened.warning:
        click.echo(opened.warning, err=True)
    try:
        _sync(opened.db, force)
    finally:
        opened.db.close()


def _sync(db: Database, force: bool) -> None:
    db.initialize()
    syncer = ScryfallSync(card_repo=CardRepository(db), cache_dir=cache_dir())

    def _progress(phase: str, current: int, total: int) -> None:
        if total <= 0:
            return
        what = " tags" if phase.endswith("_tags") else ""
        if phase.startswith("download"):
            pct = current * 100 // total
            click.echo(f"\rDownloading{what}... {pct}%", nl=False, err=True)
        else:
            click.echo(f"\rParsing{what}... {current}/{total}", nl=False, err=True)

    try:
        count = syncer.sync(force=force, progress=_progress)
    except (httpx.HTTPError, RuntimeError, sqlite3.Error) as exc:
        click.echo(err=True)  # end the in-place progress line
        raise click.ClickException(
            f"Sync failed: {describe_sync_error(exc)}"
        ) from exc
    click.echo(err=True)  # end the in-place progress line
    tags = f", {syncer.tags_loaded} oracle tags" if syncer.tags_loaded else ""
    click.echo(f"Synced {count} cards{tags}")
    if syncer.tags_error is not None:
        click.echo(
            f"Oracle tags skipped: {describe_sync_error(syncer.tags_error)}", err=True
        )
    if syncer.last_skipped:
        click.echo(f"Skipped {syncer.last_skipped} cards that failed to parse", err=True)


# A search key with its operator but no value ("mv>", "t:"). The overlay
# ignores one while it is still being typed; a finished command line
# query has no excuse, so the CLI reports it instead of searching less.
_EMPTY_TERM = re.compile(r"(?:^|(?<=[\s(-]))([A-Za-z]+(?:!=|<=|>=|:|=|<|>))(?=$|[\s)])")


@main.command(short_help="Search for cards with Scryfall-style syntax.")
@click.argument("query", nargs=-1, required=True)
@click.option(
    "--limit", "-n", default=20, type=click.IntRange(min=1), help="Max results"
)
def search(query: tuple[str, ...], limit: int) -> None:
    """Search for cards with Scryfall-style syntax, for example
    'vimtg search t:creature c:r mv<=2'. Put '--' before a query that
    starts with '-': 'vimtg search -- -t:land c:boros'."""
    from vimtg.config.settings import load_settings
    from vimtg.editor.config_options import price_text

    text = " ".join(query)
    # Quoted phrases and /regexes/ are values, not terms
    empty = _EMPTY_TERM.search(re.sub(r'"[^"]*"|/[^/]*/', "_", text))
    if empty:
        raise click.ClickException(
            f"Search term '{empty.group(1)}' needs a value (e.g. 'mv>=3', 't:creature')"
        )
    repo = _make_card_repo()
    if repo.count() == 0:
        raise click.ClickException(f"{_NO_CARD_DB} (run 'vimtg sync' first)")
    service = SearchService(card_repo=repo)
    try:
        results = service.search(text, limit=limit)
    except SearchSyntaxError as exc:
        raise click.ClickException(str(exc)) from exc

    if service.tags_unsynced(text):
        click.echo(
            f"note: {TAGS_NOT_SYNCED}; run `vimtg sync` to download them", err=True
        )
    if not results:
        click.echo("No cards found.")
        return

    settings = load_settings()
    for card in results:
        name = card.name[:30] if len(card.name) > 30 else card.name
        mana = card.mana_cost  # in full: a split card's is "{1}{R} // {1}{U}"
        type_line = card.type_line[:26] if len(card.type_line) > 26 else card.type_line
        row = f"{name:<32}{mana:<16}{type_line:<28}{card.set_code.upper():<8}"
        if settings.show_prices:
            row += f"{price_text(card, settings.price_source) or '-':>8}"
        click.echo(row.rstrip())


@main.command()
@click.argument("source", type=click.Path())
@click.option(
    "--from",
    "from_fmt",
    type=click.Choice(IMPORT_FORMAT_NAMES),
    help="Source format (auto-detected if omitted; not for a deck URL)",
)
@click.option(
    "--to",
    "to_fmt",
    type=click.Choice(tuple(FORMAT_NAMES)),
    required=True,
    help="Target format (mtga = arena; guide = sideboard plans as Markdown)",
)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--force", is_flag=True, help="Overwrite an existing output file")
def convert(
    source: str,
    from_fmt: str | None,
    to_fmt: str,
    output: str | None,
    force: bool,
) -> None:
    """Convert a deck file, or a deck-site URL, between formats.

    Card names resolve against the card database when it has been
    synced, so exports carry each card's official name. -o refuses an
    existing file unless --force is given, and never overwrites the
    input file.
    """
    from vimtg.services.deck_sources import is_deck_url

    is_url = is_deck_url(source)
    if is_url and from_fmt:
        raise click.UsageError("--from does not apply to a deck URL")
    in_path = None if is_url else Path(source)
    if in_path is not None and not in_path.exists():
        raise click.BadParameter(f"'{source}' does not exist.", param_hint="'SOURCE'")
    out_path = Path(output).expanduser() if output else None
    if out_path is not None:
        if in_path is not None and out_path.resolve() == in_path.resolve():
            raise click.ClickException(
                f"refusing to overwrite the input file {source} "
                "(choose another -o path)"
            )
        _check_output_path(out_path, force)

    card_db = _optional_card_db()
    try:
        result = _convert_text(source, in_path, from_fmt, to_fmt, card_db)
    finally:
        if card_db is not None:
            card_db.close()
    if out_path is not None:
        atomic_write_text(out_path, result)
        click.echo(f"Converted to {output}")
    else:
        click.echo(result)


def _convert_text(
    source: str,
    in_path: Path | None,
    from_fmt: str | None,
    to_fmt: str,
    card_db: Database | None,
) -> str:
    """The converted deck text (see convert); `in_path` is None when
    `source` is a deck URL."""
    from vimtg.services import deck_sources
    from vimtg.services.import_export_service import DeckFormat, ImportExportService

    service = ImportExportService(
        card_repo=CardRepository(card_db) if card_db is not None else None
    )
    if in_path is None:
        try:
            remote = deck_sources.fetch_deck(source)
        except deck_sources.DeckSourceError as exc:
            raise click.ClickException(str(exc)) from exc
        imported = service.to_vimtg(remote, url=source)
    else:
        imported = service.to_vimtg(
            in_path.read_text(encoding="utf-8"),
            fmt=FORMAT_NAMES[from_fmt] if from_fmt else None,
            name=in_path.stem,
        )
    if imported.skipped:
        # stderr, so `vimtg convert ... > out.txt` stays a clean deck
        click.echo(
            f"Skipped {len(imported.skipped)} unreadable line(s) in {source}:",
            err=True,
        )
        for skipped in imported.skipped:
            click.echo(f"  line {skipped.line_number}: {skipped.text}", err=True)
    dst_fmt = FORMAT_NAMES[to_fmt]
    if dst_fmt is DeckFormat.VIMTG:
        return imported.text
    resolved = dict(imported.resolution.resolved)
    return service.export_deck(imported.deck, dst_fmt, resolved=resolved)


def _optional_card_db() -> Database | None:
    """The synced card database, or None when there is none (or it
    cannot be opened) — conversion then works from the typed names.
    The caller closes it."""
    return _open_card_db()[0]


@main.command()
def tutor() -> None:
    """Learn vimtg in a throwaway lesson deck, like vimtutor."""
    from vimtg.tutor import LAUNCH_TUTOR

    _follow_into_tutor(LAUNCH_TUTOR)


@click.command(hidden=True)
@click.argument("path", type=click.Path())
def _open_deck(path: str) -> None:
    """`vimtg deck.deck`: open the deck in the editor (not a subcommand)."""
    _launch_editor(path)


def _launch_editor(path: str | None) -> None:
    """Launch the TUI editor for the given deck file path."""
    _follow_into_tutor(_run_editor(Path(path) if path else None))


def _run_editor(deck_path: Path | None) -> object:
    from vimtg.tui.app import VimTGApp

    return VimTGApp(deck_path=deck_path).run()


def _follow_into_tutor(result: object) -> None:
    """While the app exits asking for the tutor (:Tutor, the greeter's t),
    run it again on a fresh lesson deck in the tutor's sandbox."""
    from vimtg.tutor import LAUNCH_TUTOR, tutor_sandbox

    while result == LAUNCH_TUTOR:
        with tutor_sandbox() as deck:
            result = _run_editor(deck)

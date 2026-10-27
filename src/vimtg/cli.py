"""CLI entry point for vimtg."""

from __future__ import annotations

import errno
import re
import sqlite3
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import click
import httpx
from click.shell_completion import CompletionItem

from vimtg import __version__
from vimtg.cli_errors import friendly_error
from vimtg.cli_json import dumps, info_doc, missing_doc, search_doc, validation_doc
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
    from collections.abc import Callable

    from vimtg.domain.card import Card
    from vimtg.domain.deck import Deck, DeckEntry
    from vimtg.domain.deck_lines import MissingQuantityLine
    from vimtg.domain.validation import ValidationReport


F = TypeVar("F", bound="Callable[..., Any]")


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
            raise click.ClickException(friendly_error(exc)) from exc
        except (UnicodeDecodeError, sqlite3.Error) as exc:
            raise click.ClickException(friendly_error(exc)) from exc


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


def _json_option(schema: str) -> Callable[[F], F]:
    """The --json flag: one JSON document (`schema`) on stdout instead
    of the text output; notes stay on stderr."""
    return click.option(
        "--json", "as_json", is_flag=True,
        help=f"Print one JSON document (schema {schema}) instead of text.",
    )


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--strict",
    is_flag=True,
    help="Exit non-zero on warnings too (e.g. unknown card names); "
    "requires a card database.",
)
@_json_option("vimtg.validation/1")
def validate(path: str, strict: bool, as_json: bool) -> None:
    """Validate a deck file (format-aware when a card database exists).

    Exits 0 when the deck is valid, 1 on errors (with --strict, on
    warnings too)."""
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

    ok = not any(p.level == "error" or strict for p in report.problems)
    if as_json:
        click.echo(dumps(validation_doc(path, report, ok)))
    elif not report.problems:
        click.echo(f"{file_path.name}: ok" + (f" ({fmt})" if fmt else ""))
        if report.bracket:
            click.echo(f"{file_path.name}: info: {report.bracket}")
    else:
        _echo_problems(file_path.name, text, report)
    if not ok:
        sys.exit(1)


def _echo_problems(name: str, text: str, report: ValidationReport) -> None:
    """The text report: one `file:line: level: message` per problem."""
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
        click.echo(f"{name}:{line_part} {err.level}: {err.message}{note}")
    # Informational only: never an error, and --strict ignores it.
    if report.bracket:
        click.echo(f"{name}: info: {report.bracket}")


@main.command()
@click.argument("path", type=click.Path(exists=True))
@_json_option("vimtg.info/1")
def info(path: str, as_json: bool) -> None:
    """Show deck summary: name, format, every zone's card count, and
    (with card data) a one-line stats summary."""
    from vimtg.config.settings import load_settings
    from vimtg.data.deck_repository import missing_quantity_lines
    from vimtg.domain.analytics import compute_stats
    from vimtg.domain.validation import missing_quantity_warnings

    card_repo = _try_card_repo()
    service = DeckService(deck_repo=DeckRepository(), card_repo=card_repo)
    file_path = Path(path)
    text, deck = service.open_deck(file_path)
    settings = load_settings()
    missing = missing_quantity_lines(text)
    resolved = _resolve(card_repo, deck, missing)

    own_fmt = deck.metadata.format.strip()
    fmt = own_fmt or settings.default_format
    fmt_source = "deck" if own_fmt else "default_format" if fmt else ""
    if as_json:
        stats = (
            compute_stats(deck, resolved, settings.price_source)
            if resolved is not None else None
        )
        click.echo(dumps(info_doc(path, deck, fmt, fmt_source, stats)))
    else:
        _echo_info(deck, fmt, fmt_source, resolved, settings.price_source)
    for warning in missing_quantity_warnings(missing, resolved):
        click.echo(
            f"{file_path.name}:{warning.line_number}: warning: {warning.message}", err=True
        )


def _echo_info(
    deck: Deck,
    fmt: str,
    fmt_source: str,
    resolved: dict[str, Card] | None,
    price_source: str,
) -> None:
    """The text summary: one aligned `Label:  value` row each."""
    from vimtg.domain.analytics import stats_summary
    from vimtg.editor.config_options import currency_symbol_for

    shown = fmt or "(none)"
    if fmt and fmt_source == "default_format":
        shown = f"{fmt} (default_format)"
    rows = [("Deck", deck.metadata.name or "(unnamed)"), ("Format", shown)]
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
        symbol = currency_symbol_for(price_source)
        rows.append(("Stats", stats_summary(deck, resolved, price_source, symbol)))
    for label, value in rows:
        click.echo(f"{label + ':':<12}{value}")


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
@click.option(
    "--collection", "collection_arg", default=None, type=click.Path(),
    help="Collection CSV export (default: the `collection` setting).",
)
@_json_option("vimtg.missing/1")
def missing(path: str, collection_arg: str | None, as_json: bool) -> None:
    """Print the cards the collection lacks for this deck as 'N Card Name'
    lines (mainboard, a blank line, sideboard), ready for a store's
    mass-entry box, with the cost to complete on stderr."""
    from vimtg.config.settings import load_settings
    from vimtg.domain.collection import (
        CollectionError,
        missing_list,
        ownership,
        summarize_ownership,
    )
    from vimtg.editor.config_options import currency_symbol_for
    from vimtg.services.collection_service import collection_path, load_collection

    settings = load_settings()
    setting = collection_arg or settings.collection.strip()
    if not setting:
        click.echo(
            "No collection configured: pass --collection file.csv, or load one "
            "with :collection in the editor",
            err=True,
        )
        sys.exit(1)
    csv_path = collection_path(setting)
    try:
        collection = load_collection(csv_path)
    except CollectionError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    card_repo = _try_card_repo()
    service = DeckService(deck_repo=DeckRepository(), card_repo=card_repo)
    file_path = Path(path)
    _text, deck = service.open_deck(file_path)
    resolved = _resolve(card_repo, deck, ())
    owns = ownership(deck, collection)
    source = settings.price_source
    summary = summarize_ownership(owns, resolved or {}, source)
    if as_json:
        click.echo(dumps(missing_doc(path, str(csv_path), owns, resolved or {}, summary)))
        if resolved is None:
            click.echo(f"({_no_card_db_note()} — prices unknown; run 'vimtg sync')", err=True)
        return
    lines = missing_list(owns, resolved or {})
    if not lines:
        click.echo(f"Nothing missing: the collection covers {file_path.name}", err=True)
        return
    click.echo(lines, nl=False)
    if resolved is None:
        total = "unknown (no card database; run vimtg sync)"
    elif summary.cost_to_complete is None:
        total = f"unknown (no {source} prices)"
    else:
        total = f"{currency_symbol_for(source)}{summary.cost_to_complete:.2f} ({source})"
        if summary.unpriced_unique:
            total += f", {summary.unpriced_unique} unpriced"
    click.echo(f"Total to complete: {total}", err=True)


_DECK_OR_STDIN = click.Path(exists=True, dir_okay=False, allow_dash=True)


@main.command(name="diff")
@click.argument("old", type=_DECK_OR_STDIN)
@click.argument("new", type=_DECK_OR_STDIN)
@_json_option("vimtg.diff/1")
def diff_cmd(old: str, new: str, as_json: bool) -> None:
    """Compare two decks card by card: what was added, removed, changed
    in quantity or moved between zones, and (with card data) a stats
    line. '-' reads one side from stdin.

    Exits 0 when the decks hold the same cards, 1 when they differ and
    2 when a deck cannot be read, like diff(1)."""
    from vimtg.cli_diff import diff_decks

    sys.exit(diff_decks(old, new, _try_card_repo, as_json))


@main.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@_json_option("vimtg.combos/1")
def combos(path: str, as_json: bool) -> None:
    """Find the deck's combos, and those one card away, on Commander
    Spellbook (sends the main and commander zones' card names).

    Exits 0 on a lookup, 1 when it fails."""
    from vimtg.cli_combos import find_combos

    sys.exit(find_combos(path, as_json))


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
@_json_option("vimtg.search/1")
def search(query: tuple[str, ...], limit: int, as_json: bool) -> None:
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
    if as_json:
        click.echo(dumps(search_doc(text, results)))
        return
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
    help=(
        "Target format (mtga = arena; list = bare card lines for MPC "
        "Autofill and stores, also mpc or tcgplayer; guide = sideboard "
        "plans as Markdown)"
    ),
)
@click.option("--output", "-o", type=click.Path(), help="Output file path (- for stdout)")
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing output file, and write despite export check errors",
)
def convert(
    source: str,
    from_fmt: str | None,
    to_fmt: str,
    output: str | None,
    force: bool,
) -> None:
    """Convert a deck file, or a deck-site URL, between formats.

    Card names resolve against the card database when it has been
    synced, so exports carry each card's official name. The target's
    export checks run first: warnings go to stderr, and an error stops
    the conversion (exit 1) unless --force is given. -o refuses an
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
    out_path = Path(output).expanduser() if output and output != "-" else None
    if out_path is not None:
        if in_path is not None and out_path.resolve() == in_path.resolve():
            raise click.ClickException(
                f"refusing to overwrite the input file {source} "
                "(choose another -o path)"
            )
        _check_output_path(out_path, force)

    card_db = _optional_card_db()
    try:
        result, cards = _convert_text(source, in_path, from_fmt, to_fmt, card_db, force)
    finally:
        if card_db is not None:
            card_db.close()
    if out_path is not None:
        atomic_write_text(out_path, result, newline="")
        count = f" ({cards} cards)" if cards is not None else ""
        click.echo(f"Converted to {output}{count}")
    else:
        click.echo(result)
        if cards is not None:
            click.echo(f"{to_fmt}: {cards} cards", err=True)


def _convert_text(
    source: str,
    in_path: Path | None,
    from_fmt: str | None,
    to_fmt: str,
    card_db: Database | None,
    force: bool,
) -> tuple[str, int | None]:
    """The converted deck text (see convert) and, for a target that
    reports it, how many cards it holds; `in_path` is None when
    `source` is a deck URL."""
    from vimtg.services import deck_sources
    from vimtg.services.export_targets import (
        DeckFormat,
        IssueLevel,
        check_export,
        exported_card_count,
        target_named,
    )
    from vimtg.services.import_export_service import ImportExportService

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
    target = target_named(to_fmt)
    assert target is not None  # click.Choice admits only target names
    resolved = None if card_db is None else dict(imported.resolution.resolved)
    issues = check_export(imported.deck, resolved, target)
    for issue in issues:
        click.echo(f"{issue.level.value}: {issue.text(named=None)}", err=True)
    errors = sum(issue.level is IssueLevel.ERROR for issue in issues)
    if errors and not force:
        raise click.ClickException(
            f"{to_fmt} export refused ({errors} error{'s' if errors > 1 else ''}); "
            "--force writes it anyway"
        )
    cards = exported_card_count(imported.deck, target) if target.counts_cards else None
    if target.fmt is DeckFormat.VIMTG:
        return imported.text, cards
    return service.export(imported.deck, target, resolved=resolved), cards


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

"""CLI entry point for vimtg."""

from __future__ import annotations

import errno
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
from vimtg.data.scryfall_sync import ScryfallSync, describe_sync_error
from vimtg.domain.errors import DatabaseNotInitializedError
from vimtg.services.deck_service import DeckService
from vimtg.services.search_service import SearchService, SearchSyntaxError

if TYPE_CHECKING:
    from vimtg.domain.card import Card
    from vimtg.domain.deck import Deck


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
            f"Hint: the database at {db_path()} may be corrupt — delete it "
            "and run `vimtg sync`."
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
    ends in .deck — a new deck to be created on :w) routes to `edit`.
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
                cmd = self.get_command(ctx, "edit")
                assert cmd is not None
                return "edit", cmd, args
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
        from vimtg.tui.app import VimTGApp

        app = VimTGApp()
        app.run()


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

    if out_path.exists() and not force:
        raise click.ClickException(
            f"{out_path} already exists (use --force to overwrite)"
        )

    service = _make_service()
    text = service.new_deck(name=name, fmt=fmt)
    service.save_deck(text, out_path)
    click.echo(f"Created {out_path}")


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


def _try_card_repo() -> CardRepository | None:
    """A populated card repository, or None when no usable database exists."""
    import sqlite3

    try:
        if not db_path().exists():
            return None
        repo = _make_card_repo()
        return repo if repo.count() > 0 else None
    except (sqlite3.Error, DatabaseNotInitializedError):
        return None


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

    card_repo = _try_card_repo()
    service = DeckService(deck_repo=DeckRepository(), card_repo=card_repo)
    file_path = Path(path)
    _text, deck = service.open_deck(file_path)

    fmt = deck.metadata.format or load_settings().default_format
    resolved = None
    if card_repo is not None:
        resolved, _unresolved = service.resolve_cards(deck)
    errors = service.validate(
        deck, resolved, fmt, card_db=card_repo is not None
    )

    if strict and card_repo is None:
        click.echo(
            f"{file_path.name}: error: --strict needs a card database to "
            "check card names; run 'vimtg sync'"
        )
        sys.exit(1)
    if fmt and card_repo is None:
        click.echo(
            "(no card database — legality checks skipped; run 'vimtg sync')"
        )

    bracket_note = _bracket_note(deck, fmt, resolved)
    if not errors:
        click.echo(f"{file_path.name}: ok" + (f" ({fmt})" if fmt else ""))
        if bracket_note:
            click.echo(f"{file_path.name}: info: {bracket_note}")
        return

    has_errors = False
    for err in errors:
        line_part = f"{err.line_number}:" if err.line_number is not None else ""
        click.echo(f"{file_path.name}:{line_part} {err.level}: {err.message}")
        if err.level == "error" or strict:
            has_errors = True
    # Informational only: never an error, and --strict ignores it.
    if bracket_note:
        click.echo(f"{file_path.name}: info: {bracket_note}")

    if has_errors:
        sys.exit(1)


def _bracket_note(
    deck: Deck, fmt: str, resolved: dict[str, Card] | None
) -> str:
    """Commander-bracket estimate for `validate`, or '' when it does not
    apply (not Commander, or no card database to read Game Changers)."""
    from vimtg.domain.analytics import estimate_bracket, is_commander_deck

    if resolved is None:
        return ""
    applies = fmt.strip().lower() == "commander" if fmt else is_commander_deck(deck)
    if not applies:
        return ""
    est = estimate_bracket(deck, resolved)
    names = f" ({', '.join(est.game_changers)})" if est.game_changers else ""
    return (
        f"{est.count} Game Changers{names}; estimated Commander bracket "
        f"{est.label} (heuristic: counts Game Changers only)"
    )


@main.command()
@click.argument("path", type=click.Path(exists=True))
def info(path: str) -> None:
    """Show deck summary."""
    service = _make_service()
    file_path = Path(path)
    _text, deck = service.open_deck(file_path)

    main_entries = deck.mainboard()
    side_entries = deck.sideboard()
    main_count = sum(e.quantity for e in main_entries)
    side_count = sum(e.quantity for e in side_entries)
    main_unique = len({e.card_name for e in main_entries})
    side_unique = len({e.card_name for e in side_entries})

    click.echo(f"Deck:      {deck.metadata.name or '(unnamed)'}")
    click.echo(f"Format:    {deck.metadata.format or '(none)'}")
    click.echo(f"Mainboard: {main_count} cards ({main_unique} unique)")
    click.echo(f"Sideboard: {side_count} cards ({side_unique} unique)")


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
            "(no card database — only basic lands count as lands; run 'vimtg sync')",
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
    db = Database(db_path())
    try:
        _sync(db, force)
    finally:
        db.close()


def _sync(db: Database, force: bool) -> None:
    db.initialize()
    syncer = ScryfallSync(card_repo=CardRepository(db), cache_dir=cache_dir())

    def _progress(phase: str, current: int, total: int) -> None:
        if phase == "download" and total > 0:
            pct = current * 100 // total
            click.echo(f"\rDownloading... {pct}%", nl=False)
        elif phase == "parse" and total > 0:
            click.echo(f"\rParsing... {current}/{total}", nl=False)

    try:
        count = syncer.sync(force=force, progress=_progress)
    except (httpx.HTTPError, RuntimeError) as exc:
        click.echo()  # end the in-place progress line
        raise click.ClickException(
            f"Sync failed: {describe_sync_error(exc)}"
        ) from exc
    click.echo(f"\nSynced {count} cards")
    if syncer.last_skipped:
        click.echo(f"Skipped {syncer.last_skipped} cards that failed to parse")


@main.command()
@click.argument("query", nargs=-1, required=True)
@click.option("--limit", "-n", default=20, help="Max results")
def search(query: tuple[str, ...], limit: int) -> None:
    """Search for cards with Scryfall-style syntax, e.g.
    'vimtg search t:creature c:r mv<=2'. Put '--' before a query that
    starts with '-': 'vimtg search -- -t:land c:boros'."""
    repo = _make_card_repo()
    if repo.count() == 0:
        raise click.ClickException(str(DatabaseNotInitializedError()))
    service = SearchService(card_repo=repo)
    try:
        results = service.search(" ".join(query), limit=limit)
    except SearchSyntaxError as exc:
        raise click.ClickException(str(exc)) from exc

    if not results:
        click.echo("No cards found.")
        return

    for card in results:
        price = f"${card.price_usd:.2f}" if card.price_usd is not None else "-"
        name = card.name[:30] if len(card.name) > 30 else card.name
        mana = card.mana_cost[:14] if len(card.mana_cost) > 14 else card.mana_cost
        type_line = card.type_line[:26] if len(card.type_line) > 26 else card.type_line
        click.echo(
            f"{name:<32}{mana:<16}{type_line:<28}"
            f"{card.set_code.upper():<8}{price:>8}"
        )


@main.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option(
    "--from",
    "from_fmt",
    type=click.Choice(["mtgo", "arena", "moxfield", "archidekt"]),
    help="Source format (auto-detected if omitted)",
)
@click.option(
    "--to",
    "to_fmt",
    type=click.Choice(["vimtg", "mtgo", "arena", "moxfield", "archidekt", "guide"]),
    required=True,
    help="Target format (guide = sideboard plans as Markdown)",
)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def convert(input_path: str, from_fmt: str | None, to_fmt: str, output: str | None) -> None:
    """Convert deck between formats."""
    from vimtg.services.import_export_service import DeckFormat, ImportExportService

    service = ImportExportService()
    text = Path(input_path).read_text(encoding="utf-8")
    src_fmt = DeckFormat(from_fmt) if from_fmt else None
    report = service.import_deck_report(text, src_fmt)
    if report.skipped:
        # stderr, so `vimtg convert ... > out.txt` stays a clean deck
        click.echo(
            f"Skipped {len(report.skipped)} unreadable line(s) in {input_path}:",
            err=True,
        )
        for skipped in report.skipped:
            click.echo(f"  line {skipped.line_number}: {skipped.text}", err=True)
    result = service.export_deck(report.deck, DeckFormat(to_fmt))
    if output:
        Path(output).write_text(result, encoding="utf-8")
        click.echo(f"Converted to {output}")
    else:
        click.echo(result)


@main.command()
@click.argument("path", type=click.Path(), required=False)
def edit(path: str | None = None) -> None:
    """Open deck in TUI editor."""
    _launch_editor(path)


def _launch_editor(path: str | None) -> None:
    """Launch the TUI editor for the given deck file path."""
    from vimtg.tui.app import VimTGApp

    deck_path = Path(path) if path else None
    app = VimTGApp(deck_path=deck_path)
    app.run()

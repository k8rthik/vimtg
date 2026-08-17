"""CLI entry point for vimtg."""

from __future__ import annotations

import sys
from pathlib import Path

import click
import httpx

from vimtg import __version__
from vimtg.config.paths import cache_dir, db_path
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.deck_repository import DeckRepository
from vimtg.data.scryfall_sync import ScryfallSync
from vimtg.domain.errors import DatabaseNotInitializedError
from vimtg.services.deck_service import DeckService
from vimtg.services.search_service import SearchService


def _make_service() -> DeckService:
    return DeckService(deck_repo=DeckRepository())


def _make_card_repo() -> CardRepository:
    db = Database(db_path())
    db.initialize()
    return CardRepository(db)


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


@click.group(cls=_DeckFileGroup, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="vimtg")
@click.pass_context
def main(ctx: click.Context) -> None:
    """vimtg — Vim-powered MTG deck builder."""
    if ctx.invoked_subcommand is None:
        from vimtg.tui.app import VimTGApp

        app = VimTGApp()
        app.run()


@main.command()
@click.argument("name")
@click.option("--format", "-f", "fmt", default="", help="MTG format")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def new(name: str, fmt: str, output: str | None) -> None:
    """Create a new deck file."""
    service = _make_service()
    text = service.new_deck(name=name, fmt=fmt)

    out_path = Path(output) if output else Path.cwd() / f"{name}.deck"

    service.save_deck(text, out_path)
    click.echo(f"Created {out_path}")


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
def validate(path: str) -> None:
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
    errors = service.validate(deck, resolved, fmt)

    if fmt and card_repo is None:
        click.echo(
            "(no card database — legality checks skipped; run 'vimtg sync')"
        )

    if not errors:
        click.echo(f"{file_path.name}: ok" + (f" ({fmt})" if fmt else ""))
        return

    has_errors = False
    for err in errors:
        line_part = f"{err.line_number}:" if err.line_number is not None else ""
        click.echo(f"{file_path.name}:{line_part} {err.level}: {err.message}")
        if err.level == "error":
            has_errors = True

    if has_errors:
        sys.exit(1)


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


@main.command(name="sync")
@click.option("--force", is_flag=True, help="Force re-download")
def sync_cmd(force: bool) -> None:
    """Download card data from Scryfall."""
    repo = _make_card_repo()
    syncer = ScryfallSync(card_repo=repo, cache_dir=cache_dir())

    def _progress(phase: str, current: int, total: int) -> None:
        if phase == "download" and total > 0:
            pct = current * 100 // total
            click.echo(f"\rDownloading... {pct}%", nl=False)
        elif phase == "parse" and total > 0:
            click.echo(f"\rParsing... {current}/{total}", nl=False)

    try:
        count = syncer.sync(force=force, progress=_progress)
    except httpx.HTTPError as exc:
        raise click.ClickException(f"Network error during sync: {exc}") from exc
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"\nSynced {count} cards")
    if syncer.last_skipped:
        click.echo(f"Skipped {syncer.last_skipped} cards that failed to parse")


@main.command()
@click.argument("query")
@click.option("--limit", "-n", default=20, help="Max results")
def search(query: str, limit: int) -> None:
    """Search for cards."""
    repo = _make_card_repo()
    if repo.count() == 0:
        raise click.ClickException(str(DatabaseNotInitializedError()))
    service = SearchService(card_repo=repo)
    results = service.fuzzy_search(query, limit=limit)

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
    type=click.Choice(["vimtg", "mtgo", "arena", "moxfield", "archidekt"]),
    required=True,
    help="Target format",
)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def convert(input_path: str, from_fmt: str | None, to_fmt: str, output: str | None) -> None:
    """Convert deck between formats."""
    from vimtg.services.import_export_service import DeckFormat, ImportExportService

    service = ImportExportService()
    text = Path(input_path).read_text(encoding="utf-8")
    src_fmt = DeckFormat(from_fmt) if from_fmt else None
    deck = service.import_deck(text, src_fmt)
    result = service.export_deck(deck, DeckFormat(to_fmt))
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

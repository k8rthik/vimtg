"""`vimtg diff`: two decks compared card by card, with diff(1)'s exit
codes (0 same cards, 1 different, 2 trouble)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import click

from vimtg.cli_errors import friendly_error
from vimtg.cli_json import diff_doc, dumps
from vimtg.domain.deck import DeckSection
from vimtg.domain.deck_diff import ChangeType, DeckDiff, StatsDelta
from vimtg.services.deck_diff_service import DeckDiffService

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository

_ZONE_LABELS = {
    DeckSection.MAIN: "Mainboard",
    DeckSection.SIDEBOARD: "Sideboard",
    DeckSection.COMMANDER: "Commander",
    DeckSection.COMPANION: "Companion",
    DeckSection.MAYBEBOARD: "Maybeboard",
}


class _TroubleError(click.ClickException):
    """A file that cannot be read: exit 2, as diff(1) does."""

    exit_code = 2


def _read(path: str) -> str:
    try:
        if path == "-":
            return sys.stdin.read()
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _TroubleError(f"{path}: {friendly_error(exc)}") from exc


def _change_line(change_type: ChangeType, name: str, old: str, new: str) -> str:
    """One change, worded as the history overlay's Diff panel words it."""
    if change_type is ChangeType.ADDED:
        return f"  + {new} {name}"
    if change_type is ChangeType.REMOVED:
        return f"  - {old} {name}"
    if change_type is ChangeType.SECTION_MOVED:
        return f"  ⇄ {name}  {old} → {new}"
    return f"  ~ {name}  {old} → {new}"


def _text_lines(diff: DeckDiff) -> list[str]:
    lines: list[str] = []
    zone: DeckSection | None = None
    for c in diff.changed_cards():
        if c.section is not zone:
            zone = c.section
            lines.append(f"{_ZONE_LABELS[zone]}:")
        if c.change_type is ChangeType.SECTION_MOVED:
            old = (c.old_section or zone).value
            new = (c.new_section or zone).value
        else:
            old, new = str(c.old_quantity), str(c.new_quantity)
        lines.append(_change_line(c.change_type, c.card_name, old, new))
    return lines


def _stats_line(delta: StatsDelta, price_source: str, symbol: str) -> str:
    def price(value: float | None) -> str:
        return "-" if value is None else f"{symbol}{value:.2f}"

    parts = [
        f"Stats: {delta.old_total} → {delta.new_total} cards",
        f"Avg CMC {delta.old_avg_cmc:.2f} → {delta.new_avg_cmc:.2f}",
    ]
    if delta.old_price is not None or delta.new_price is not None:
        parts.append(f"{price(delta.old_price)} → {price(delta.new_price)} ({price_source})")
    return " | ".join(parts)


def diff_decks(
    old: str,
    new: str,
    card_repo: Callable[[], CardRepository | None],
    as_json: bool,
) -> int:
    """Print the diff from `old` to `new` ('-' is stdin) and return the
    exit code. `card_repo` opens the card database for the stats line."""
    from vimtg.config.settings import load_settings
    from vimtg.editor.config_options import currency_symbol_for

    if old == new == "-":
        raise click.UsageError("only one side can be read from stdin ('-')")
    old_text, new_text = _read(old), _read(new)
    price_source = load_settings().price_source
    diff = DeckDiffService(card_repo()).diff(old_text, new_text, price_source)
    if as_json:
        click.echo(dumps(diff_doc(old, new, diff, price_source)))
    elif diff.has_changes:
        lines = _text_lines(diff)
        if diff.stats_delta is not None:
            symbol = currency_symbol_for(price_source)
            lines.append(_stats_line(diff.stats_delta, price_source, symbol))
        click.echo("\n".join(lines))
    if not diff.has_changes and old_text != new_text:
        click.echo("(same cards; the files differ in lines that are not cards)", err=True)
    return 1 if diff.has_changes else 0

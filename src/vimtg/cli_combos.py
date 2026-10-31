"""`vimtg combos`: the deck's combos and those one card away, through
Commander Spellbook. Exit 0 on a lookup, 1 when it fails."""

from __future__ import annotations

from pathlib import Path

import click

from vimtg.cli_json import combos_doc, dumps
from vimtg.config.paths import cache_dir
from vimtg.data.deck_repository import parse_deck_text
from vimtg.services.spellbook import (
    SERVICE,
    SITE_URL,
    Combo,
    ComboReport,
    SpellbookClient,
    SpellbookError,
)


def combo_line(combo: Combo) -> str:
    """`742-1295  A + B  →  Win the game`, plus `(add C)` when one away."""
    line = f"{combo.id}  {' + '.join(combo.cards)}  →  {', '.join(combo.produces) or '?'}"
    if combo.missing:
        line += f"  (add {', '.join(combo.missing)})"
    return line


def report_lines(report: ComboReport) -> list[str]:
    lines: list[str] = []
    for title, combos in (
        ("In this deck", report.included), ("One card away", report.one_away),
    ):
        lines.append(f"{title} ({len(combos)}):")
        lines.extend(f"  {combo_line(c)}" for c in combos)
        if not combos:
            lines.append("  (none)")
    lines.append(f"Combo data from {SERVICE}: {SITE_URL}")
    return lines


def find_combos(path: str, as_json: bool) -> int:
    """Print the deck's combos and return the exit code."""
    deck = parse_deck_text(Path(path).read_text(encoding="utf-8"))
    try:
        report = SpellbookClient(cache_dir=cache_dir()).find(deck)
    except SpellbookError as exc:
        click.echo(f"Error: {exc}", err=True)
        return 1
    if report.note:
        click.echo(f"({report.note})", err=True)
    if as_json:
        click.echo(dumps(combos_doc(path, report)))
    else:
        click.echo("\n".join(report_lines(report)))
    return 0

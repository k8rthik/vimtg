""":stats names the price source it totals."""

from __future__ import annotations

from vimtg.config.settings import Settings
from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.deck_cmds import cmd_stats
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _bolt() -> Card:
    return Card.from_scryfall({
        "id": "b", "name": "Lightning Bolt", "type_line": "Instant",
        "mana_cost": "{R}", "cmc": 1.0,
        "prices": {"usd": "2.00", "eur": "1.50", "tix": "0.10"},
    })


def _run(settings: Settings | None) -> str:
    ctx = EditorContext()
    ctx.resolved_cards = {"Lightning Bolt": _bolt()}
    if settings is not None:
        ctx.settings = settings
    cmd_stats(
        Buffer.from_text("4 Lightning Bolt\n"), Cursor(row=0),
        ParsedCommand(name="stats"), ctx,
    )
    return ctx.message


def test_default_price_source_is_labelled() -> None:
    assert "$8.00 (usd)" in _run(None)


def test_configured_price_source_is_used() -> None:
    assert "€6.00 (eur)" in _run(Settings(price_source="eur"))

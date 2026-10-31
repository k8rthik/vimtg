"""Side-pane commands: :analytics, :edhrec, :close.

TUI-agnostic: zero Textual imports. Handlers only describe what should
open via EditorContext; MainScreen owns the pane widgets.
"""

from __future__ import annotations

from vimtg.data.deck_repository import parse_deck_text
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.lint import effective_format
from vimtg.editor.splits import EdhrecOpen

# :edhrec tab argument → tab label prefix in the recommendations panel
_EDHREC_TAB_ARGS: dict[str, str] = {
    "top": "Top",
    "creature": "Creatures",
    "creatures": "Creatures",
    "instant": "Instants",
    "instants": "Instants",
    "sorcery": "Sorceries",
    "sorceries": "Sorceries",
    "artifact": "Artifacts",
    "artifacts": "Artifacts",
    "enchantment": "Enchantments",
    "enchantments": "Enchantments",
    "planeswalker": "Planeswalkers",
    "planeswalkers": "Planeswalkers",
    "battle": "Battles",
    "battles": "Battles",
    "land": "Lands",
    "lands": "Lands",
}


def cmd_close(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:close — close the side pane."""
    ctx.split_close = True
    return buf, cursor


def cmd_edhrec(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:edhrec [type] — EDHREC recommendations for the deck's commander.

    Commander-only: the deck must declare // Format: commander (or no
    format at all) and have at least one CMD: line. The optional
    argument picks the initial card-type tab.
    """
    arg = cmd.args.strip().lower()
    initial_tab = ""
    if arg:
        tab = _EDHREC_TAB_ARGS.get(arg)
        if tab is None:
            ctx.fail(
                f"Unknown card type: {arg} "
                "(creature/instant/sorcery/artifact/enchantment/"
                "planeswalker/battle/land/top)"
            )
            return buf, cursor
        initial_tab = tab

    deck = parse_deck_text(buf.to_text())
    default_format = getattr(ctx.settings, "default_format", "") or ""
    fmt = effective_format(deck, default_format).lower()
    if fmt not in ("", "commander"):
        ctx.fail(
            f"EDHREC is Commander-only (deck format is {fmt}; "
            "set // Format: commander)"
        )
        return buf, cursor

    commanders = tuple(entry.card_name for entry in deck.commanders())
    if not commanders:
        ctx.fail("No commander (add a CMD: line first)")
        return buf, cursor

    ctx.edhrec_open = EdhrecOpen(commanders=commanders, initial_tab=initial_tab)
    return buf, cursor


def cmd_analytics(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:analytics — live deck-analytics pane beside the deck.

    Curve, type/zone/category counts, mana-base check, and draw odds
    that follow the cursor's card; updates as the deck is edited.
    """
    ctx.analytics_open = True
    return buf, cursor


def register_split_commands(registry: CommandRegistry) -> None:
    """Register the pane ex commands: :close, :edhrec, :analytics."""
    registry.register("close", cmd_close)
    registry.register("edhrec", cmd_edhrec, aliases=["rec"])
    registry.register("analytics", cmd_analytics, aliases=["ana"])

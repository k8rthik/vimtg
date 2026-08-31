"""Split-view commands: :vsplit, :split, :close, :edhrec.

TUI-agnostic: zero Textual imports. Handlers only describe what should
open via EditorContext; MainScreen owns the split-pane widgets.
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
from vimtg.editor.splits import (
    AnalyticsOpen,
    EdhrecOpen,
    SplitDirection,
    SplitOpen,
    resolve_deck_path,
)

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


def _open_split(
    buf: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
    direction: SplitDirection,
    usage: str,
) -> tuple[Buffer, Cursor]:
    arg = cmd.args.strip()
    if not arg:
        ctx.fail(usage)
        return buf, cursor
    path = resolve_deck_path(arg, ctx.file_path)
    if path is None:
        ctx.fail(f"Cannot open {arg}: file not found")
        return buf, cursor
    ctx.split_open = SplitOpen(direction=direction, path=path)
    return buf, cursor


def cmd_vsplit(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:vsplit deck — open another deck beside this one (read-only)."""
    return _open_split(
        buf, cursor, cmd, ctx, SplitDirection.VERTICAL,
        "Usage: :vsplit <deck-file>",
    )


def cmd_split(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:split deck — open another deck below this one (read-only)."""
    return _open_split(
        buf, cursor, cmd, ctx, SplitDirection.HORIZONTAL,
        "Usage: :split <deck-file>",
    )


def cmd_close(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:close — close the split pane (alias :only)."""
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
    ctx.analytics_open = AnalyticsOpen()
    return buf, cursor


def register_split_commands(registry: CommandRegistry) -> None:
    """Register the split-view, EDHREC, and analytics ex commands."""
    registry.register("vsplit", cmd_vsplit, aliases=["vsp", "vs"])
    registry.register("split", cmd_split, aliases=["sp", "hsplit"])
    registry.register("close", cmd_close, aliases=["only"])
    registry.register("edhrec", cmd_edhrec, aliases=["rec"])
    registry.register("analytics", cmd_analytics, aliases=["ana"])

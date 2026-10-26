""":combos — open the Commander Spellbook combos overlay.

TUI-agnostic: zero Textual imports. The handler refuses a deck with no
cards to look up; the TUI owns the overlay and the lookup.
"""

from __future__ import annotations

from vimtg.data.deck_repository import parse_deck_text
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import CommandRegistry, EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor
from vimtg.services.spellbook import deck_query


def cmd_combos(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:combos — the deck's combos and those one card away."""
    query = deck_query(parse_deck_text(buf.to_text()))
    if not query.main and not query.commanders:
        ctx.fail("No cards in the deck to look up")
        return buf, cursor
    ctx.ui_request = "combos"
    return buf, cursor


def register_combo_commands(registry: CommandRegistry) -> None:
    """Register :combos."""
    registry.register("combos", cmd_combos, aliases=["combo"], takes_args=False)

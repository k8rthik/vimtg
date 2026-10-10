""":hand — open the sample-hand / goldfish overlay.

TUI-agnostic: zero Textual imports. The handler builds the library
(post-board when a sideboard plan is active) and describes what to
show through EditorContext.hand_open; the TUI owns the overlay.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card_names import CardMap
from vimtg.domain.sample_hand import HandSource, build_source
from vimtg.domain.sideboard_plan import find_plan
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.lint import effective_format

USAGE = "Usage: :hand [seed=N]"


@dataclass(frozen=True)
class HandOpen:
    """Request to open the sample-hand overlay."""

    source: HandSource
    seed: int | None = None
    mana_costs: dict[str, str] = field(default_factory=dict)


def parse_seed(args: str) -> int | None:
    """The seed from ':hand seed=42' (or ':hand 42'); None when absent.

    Raises ValueError for anything else.
    """
    arg = args.strip()
    if not arg:
        return None
    key, sep, value = arg.partition("=")
    if sep:
        if key.strip().lower() != "seed":
            raise ValueError(arg)
        arg = value.strip()
    try:
        return int(arg)
    except ValueError:
        raise ValueError(arg) from None


def cmd_hand(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:hand [seed=N] — draw a sample opening hand from the main deck.

    Uses the active sideboard plan's post-board deck. A seed makes the
    shuffles repeatable.
    """
    try:
        seed = parse_seed(cmd.args)
    except ValueError:
        ctx.fail(USAGE)
        return buf, cursor

    deck = parse_deck_text(buf.to_text())
    plan = find_plan(deck, ctx.active_plan) if ctx.active_plan else None
    default_format = getattr(ctx.settings, "default_format", "") or ""
    source = build_source(
        deck,
        ctx.resolved_cards,
        effective_format(deck, default_format),
        plan,
    )
    if not source.library:
        ctx.fail("No cards in the main deck")
        return buf, cursor

    cards = CardMap(ctx.resolved_cards) if ctx.resolved_cards else CardMap()
    mana_costs = {}
    for name in set(source.library):
        card = cards.get(name)
        if card is not None and card.mana_cost:
            mana_costs[name] = card.mana_cost
    ctx.hand_open = HandOpen(source=source, seed=seed, mana_costs=mana_costs)
    return buf, cursor


def register_hand_commands(registry: CommandRegistry) -> None:
    """Register :hand."""
    registry.register("hand", cmd_hand, aliases=["goldfish"])

"""Rendering logic for deck buffer lines as Rich Text objects.

Extracts all visual formatting from the DeckView widget to keep it small.
Handles card lines, comments, sections, and inline card expansion.
"""

from __future__ import annotations

import re

from rich.text import Text

from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer, LineType
from vimtg.tui.theme import COLORS

MANA_COLORS: dict[str, str] = {
    "W": f"bold {COLORS['mana_white']}",
    "U": f"bold {COLORS['mana_blue']}",
    "B": f"bold {COLORS['mana_black']}",
    "R": f"bold {COLORS['mana_red']}",
    "G": f"bold {COLORS['mana_green']}",
}

_MANA_RE = re.compile(r"\{([^}]+)\}")
_CURSOR_STYLE = f"on {COLORS['cursor_bg']}"
_COMMENT_STYLE = f"dim italic {COLORS['comment']}"
_EXPANSION_STYLE = f"dim {COLORS['expansion']}"


def render_line(
    line_idx: int,
    buf: Buffer,
    cursor_row: int,
    resolved: dict[str, Card],
) -> list[Text]:
    """Render a buffer line as Rich Text objects.

    Returns 1 line normally, or 1+expansion lines if the cursor
    is on this card and the card is resolved.
    """
    bl = buf.get_line(line_idx)
    is_cursor = line_idx == cursor_row
    lines: list[Text] = []

    if bl.line_type == LineType.BLANK:
        lines.append(Text(""))
    elif bl.line_type in (LineType.COMMENT, LineType.SECTION_HEADER, LineType.METADATA):
        t = Text(f"  {bl.text}", style=_COMMENT_STYLE)
        if is_cursor:
            t.stylize(_CURSOR_STYLE)
        lines.append(t)
    elif bl.line_type in (LineType.CARD_ENTRY, LineType.SIDEBOARD_ENTRY, LineType.COMMANDER_ENTRY):
        lines.extend(_render_card_line(line_idx, buf, is_cursor, resolved))
    else:
        t = Text(f"  {bl.text}")
        if is_cursor:
            t.stylize(_CURSOR_STYLE)
        lines.append(t)

    return lines


def _render_card_line(
    line_idx: int,
    buf: Buffer,
    is_cursor: bool,
    resolved: dict[str, Card],
) -> list[Text]:
    """Build the formatted card line and optional inline expansion."""
    bl = buf.get_line(line_idx)
    card_name = buf.card_name_at(line_idx)
    qty = buf.quantity_at(line_idx)
    card = resolved.get(card_name or "") if card_name else None

    t = Text()
    prefix = ">" if is_cursor else " "
    t.append(f"{prefix} ", style="bold" if is_cursor else "")

    if bl.line_type == LineType.SIDEBOARD_ENTRY:
        t.append("SB: ", style=COLORS["sideboard"])
    elif bl.line_type == LineType.COMMANDER_ENTRY:
        t.append("CMD: ", style=COLORS["sideboard"])

    t.append(f"{qty or '?':<4}", style=COLORS["quantity"])
    name_str = card_name or bl.text.strip()
    t.append(f"{name_str:<26}", style="bold" if is_cursor else "")

    if card:
        t.append(format_mana(card.mana_cost))
        type_short = card.type_line.split("\u2014")[0].strip()[:20]
        t.append(f"  {type_short}", style="dim")

    if is_cursor:
        t.stylize(_CURSOR_STYLE)

    lines: list[Text] = [t]

    if is_cursor and card:
        lines.extend(_render_expansion(card))

    return lines


def _render_expansion(card: Card) -> list[Text]:
    """Render 2-4 expansion lines showing card details."""
    lines: list[Text] = []

    type_str = card.type_line
    if card.power and card.toughness:
        type_str += f"  {card.power}/{card.toughness}"
    lines.append(Text(f"  \u2502    {type_str}", style=_EXPANSION_STYLE))

    if card.oracle_text:
        for text_line in card.oracle_text.split("\n"):
            lines.append(Text(f"  \u2502    {text_line}", style=_EXPANSION_STYLE))

    meta_parts: list[str] = []
    if card.set_code:
        meta_parts.append(f"Set: {card.set_code.upper()}")
    meta_parts.append(f"Rarity: {card.rarity.value.title()}")
    if card.price_usd is not None:
        meta_parts.append(f"${card.price_usd:.2f}")
    lines.append(Text(f"  \u2502    {'  '.join(meta_parts)}", style=_EXPANSION_STYLE))

    return lines


def format_mana(mana_cost: str) -> Text:
    """Format mana cost with per-symbol colors: {R} red, {U} blue, etc."""
    t = Text()
    if not mana_cost:
        t.append("     ")
        return t

    pos = 0
    for m in _MANA_RE.finditer(mana_cost):
        if m.start() > pos:
            t.append(mana_cost[pos : m.start()])
        symbol = m.group(1)
        style = MANA_COLORS.get(symbol, COLORS["mana_colorless"])
        t.append(f"{{{symbol}}}", style=style)
        pos = m.end()

    if pos < len(mana_cost):
        t.append(mana_cost[pos:])

    return t

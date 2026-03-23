"""Rendering logic for deck buffer lines as Rich Text objects.

Extracts all visual formatting from the DeckView widget to keep it small.
Handles card lines, comments, sections, and inline card expansion.
"""

from __future__ import annotations

import os
import re
import textwrap

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


def _line_number_gutter(
    line_idx: int, cursor_row: int, buf: Buffer,
) -> Text:
    """Render a line number gutter: relative numbers with absolute at cursor.

    Blank lines get an empty gutter. Relative numbers count only non-blank
    lines between cursor and target — matching how j/k navigate.
    """
    width = max(3, len(str(buf.line_count())))

    # Blank lines get no number
    if buf.get_line(line_idx).line_type == LineType.BLANK:
        return Text(f"{' ' * width} ")

    if line_idx == cursor_row:
        num_str = str(line_idx + 1).rjust(width)
        return Text(f"{num_str} ", style=f"bold {COLORS['quantity']}")

    # Count non-blank lines between cursor and this line
    if line_idx > cursor_row:
        non_blank = sum(
            1 for i in range(cursor_row + 1, line_idx + 1)
            if buf.get_line(i).line_type != LineType.BLANK
        )
    else:
        non_blank = sum(
            1 for i in range(line_idx, cursor_row)
            if buf.get_line(i).line_type != LineType.BLANK
        )

    num_str = str(non_blank).rjust(width)
    return Text(f"{num_str} ", style=f"dim {COLORS['comment']}")


def render_line(
    line_idx: int,
    buf: Buffer,
    cursor_row: int,
    resolved: dict[str, Card],
    show_line_numbers: bool = True,
) -> list[Text]:
    """Render a buffer line as Rich Text objects.

    Returns 1 line normally, or 1+expansion lines if the cursor
    is on this card and the card is resolved.
    """
    bl = buf.get_line(line_idx)
    is_cursor = line_idx == cursor_row
    if show_line_numbers:
        gutter = _line_number_gutter(line_idx, cursor_row, buf)
        gutter_pad = Text(" " * len(gutter.plain))
    else:
        gutter = Text("")
        gutter_pad = Text("")
    lines: list[Text] = []

    if bl.line_type == LineType.BLANK:
        t = Text()
        t.append(gutter)
        lines.append(t)
    elif bl.line_type in (LineType.COMMENT, LineType.SECTION_HEADER, LineType.METADATA):
        t = Text()
        t.append(gutter)
        t.append(f"{bl.text}", style=_COMMENT_STYLE)
        if is_cursor:
            t.stylize(_CURSOR_STYLE)
        lines.append(t)
    elif bl.line_type in (LineType.CARD_ENTRY, LineType.SIDEBOARD_ENTRY, LineType.COMMANDER_ENTRY):
        lines.extend(_render_card_line(line_idx, buf, is_cursor, resolved, gutter, gutter_pad))
    else:
        t = Text()
        t.append(gutter)
        t.append(f"{bl.text}")
        if is_cursor:
            t.stylize(_CURSOR_STYLE)
        lines.append(t)

    return lines


def _render_card_line(
    line_idx: int,
    buf: Buffer,
    is_cursor: bool,
    resolved: dict[str, Card],
    gutter: Text | None = None,
    gutter_pad: Text | None = None,
) -> list[Text]:
    """Build the formatted card line and optional inline expansion."""
    bl = buf.get_line(line_idx)
    card_name = buf.card_name_at(line_idx)
    qty = buf.quantity_at(line_idx)
    card = resolved.get(card_name or "") if card_name else None

    t = Text()
    if gutter:
        t.append(gutter)
    prefix = ">" if is_cursor else " "
    t.append(f"{prefix}", style="bold" if is_cursor else "")

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
        lines.extend(_render_expansion(card, gutter_pad))

    return lines


def _render_expansion(card: Card, gutter_pad: Text | None = None) -> list[Text]:
    """Render expansion lines with proper word-wrapping to avoid broken indentation."""
    lines: list[Text] = []
    pad = gutter_pad.plain if gutter_pad else ""
    prefix = f"{pad} \u2502    "
    prefix_len = len(prefix)

    # Terminal width — leave margin for safety
    try:
        term_width = max(40, os.get_terminal_size().columns - 2)
    except OSError:
        term_width = 78
    wrap_width = term_width - prefix_len

    type_str = card.type_line
    if card.power and card.toughness:
        type_str += f"  {card.power}/{card.toughness}"
    lines.append(Text(f"{prefix}{type_str}", style=_EXPANSION_STYLE))

    if card.oracle_text:
        for text_line in card.oracle_text.split("\n"):
            wrapped = textwrap.wrap(text_line, width=max(20, wrap_width))
            for wl in wrapped or [""]:
                lines.append(Text(f"{prefix}{wl}", style=_EXPANSION_STYLE))

    meta_parts: list[str] = []
    if card.set_code:
        meta_parts.append(f"Set: {card.set_code.upper()}")
    meta_parts.append(f"Rarity: {card.rarity.value.title()}")
    if card.price_usd is not None:
        meta_parts.append(f"${card.price_usd:.2f}")
    lines.append(Text(f"{prefix}{'  '.join(meta_parts)}", style=_EXPANSION_STYLE))

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

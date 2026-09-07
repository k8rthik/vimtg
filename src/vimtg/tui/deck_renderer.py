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
from vimtg.domain.validation import ValidationError
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.header_counts import HeaderCount
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
_COUNT_STYLE = f"dim {COLORS['quantity']}"
_PLAN_HEADER_STYLE = f"bold {COLORS['sideboard']}"
_OUT_STYLE = f"bold {COLORS['error']}"
_IN_STYLE = f"bold {COLORS['success']}"
_UNBALANCED_STYLE = f"bold {COLORS['warning']}"


def _count_annotation(line_type: LineType, count: HeaderCount) -> str:
    """Visual card-total suffix for a header line — '(12)' on section
    and zone headers, '· 60 cards' on the '// Deck:' title line,
    '· 60/15 cards' (main/side) when the deck has a sideboard, or
    '(-4 +4)' on a sideboard-plan header."""
    if count.plan:
        return f"  (-{count.outs} +{count.ins})"
    if line_type == LineType.METADATA:
        if count.side:
            return f"  · {count.main}/{count.side} cards"
        return f"  · {count.main} cards"
    return f"  ({count.main})"


def _delta_style(delta: int) -> str:
    return _OUT_STYLE if delta < 0 else _IN_STYLE


def _lint_sign(err: ValidationError | None) -> Text:
    """Two-char sign column: '✗ ' error, '! ' warning, '  ' clean.

    The column is always reserved so signs appearing and disappearing
    never shift the layout.
    """
    if err is None:
        return Text("  ")
    if err.level == "error":
        return Text("✗ ", style=f"bold {COLORS['error']}")
    return Text("! ", style=f"bold {COLORS['warning']}")


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
    price_source: str = "usd",
    currency_symbol: str = "$",
    show_prices: bool = True,
    auto_expand: bool = True,
    dimmed: bool = False,
    width: int | None = None,
    line_error: ValidationError | None = None,
    header_count: HeaderCount | None = None,
    plan_delta: int | None = None,
) -> list[Text]:
    """Render a buffer line as Rich Text objects.

    Returns 1 line normally, or 1+expansion lines if the cursor
    is on this card, the card is resolved, and auto_expand is on.
    `dimmed` renders the line de-emphasized (tag filter mismatch)
    and suppresses expansion. `line_error` puts a ✗/! sign in the
    gutter. `header_count` appends a card total to header lines
    (see editor.header_counts); it is ignored on other line types.
    `plan_delta` appends the active sideboard plan's -N/+N for this
    deck card (see editor.plan_ops.row_deltas).
    """
    bl = buf.get_line(line_idx)
    is_cursor = line_idx == cursor_row
    gutter = _lint_sign(line_error)
    if show_line_numbers:
        gutter.append_text(_line_number_gutter(line_idx, cursor_row, buf))
    gutter_pad = Text(" " * len(gutter.plain))
    lines: list[Text] = []

    if bl.line_type == LineType.BLANK:
        t = Text()
        t.append(gutter)
        lines.append(t)
    elif bl.line_type in (LineType.COMMENT, LineType.SECTION_HEADER, LineType.METADATA):
        t = Text()
        t.append(gutter)
        t.append(f"{bl.text}", style=_COMMENT_STYLE)
        if header_count is not None and bl.line_type != LineType.COMMENT:
            t.append(_count_annotation(bl.line_type, header_count), style=_COUNT_STYLE)
        if is_cursor:
            t.stylize(_CURSOR_STYLE)
        lines.append(t)
    elif bl.line_type == LineType.PLAN_HEADER:
        t = Text()
        t.append(gutter)
        t.append(f"{bl.text}", style=_PLAN_HEADER_STYLE)
        if header_count is not None:
            t.append(_count_annotation(bl.line_type, header_count), style=_COUNT_STYLE)
            if header_count.unbalanced:
                t.append(" !", style=_UNBALANCED_STYLE)
        if is_cursor:
            t.stylize(_CURSOR_STYLE)
        lines.append(t)
    elif bl.line_type in (
        LineType.CARD_ENTRY, LineType.SIDEBOARD_ENTRY,
        LineType.MAYBEBOARD_ENTRY, LineType.COMMANDER_ENTRY,
        LineType.COMPANION_ENTRY, LineType.PLAN_ENTRY,
    ):
        lines.extend(_render_card_line(
            line_idx, buf, is_cursor, resolved, gutter, gutter_pad,
            price_source=price_source, currency_symbol=currency_symbol,
            show_prices=show_prices, auto_expand=auto_expand and not dimmed,
            width=width, plan_delta=plan_delta,
        ))
        if dimmed:
            for line in lines:
                line.stylize("dim")
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
    price_source: str = "usd",
    currency_symbol: str = "$",
    show_prices: bool = True,
    auto_expand: bool = True,
    width: int | None = None,
    plan_delta: int | None = None,
) -> list[Text]:
    """Build the formatted card line and optional inline expansion."""
    bl = buf.get_line(line_idx)
    card_name = buf.card_name_at(line_idx)
    qty = buf.quantity_at(line_idx)
    card = resolved.get(card_name or "") if card_name else None
    plan_sign = buf.plan_sign_at(line_idx)

    t = Text()
    if gutter:
        t.append(gutter)
    t.append(" ")

    # A line inside a Python-style zone block has no prefix of its own —
    # render its indentation instead of synthesizing a label; the block
    # header above already names the zone.
    stripped = bl.text.lstrip()
    if plan_sign is not None:
        # Plan entry: indentation, then the signed count in its own cell
        # ('-4 ' out in red, '+3 ' in in green, '?2 ' for a missing sign)
        t.append(bl.text[: len(bl.text) - len(stripped)])
        cell = f"{plan_sign or '?'}{qty if qty is not None else '?'}"
        style = (
            _delta_style(-1 if plan_sign == "-" else 1)
            if plan_sign else _UNBALANCED_STYLE
        )
        t.append(f"{cell:<4}", style=style)
    elif not stripped.upper().startswith(("SB:", "MB:", "CMD:", "CMP:")):
        t.append(bl.text[: len(bl.text) - len(stripped)])
    elif bl.line_type == LineType.SIDEBOARD_ENTRY:
        t.append("SB: ", style=COLORS["sideboard"])
    elif bl.line_type == LineType.MAYBEBOARD_ENTRY:
        t.append("MB: ", style=COLORS["maybeboard"])
    elif bl.line_type == LineType.COMMANDER_ENTRY:
        t.append("CMD: ", style=COLORS["sideboard"])
    elif bl.line_type == LineType.COMPANION_ENTRY:
        t.append("CMP: ", style=COLORS["companion"])

    if plan_sign is None:
        t.append(f"{qty or '?':<4}", style=COLORS["quantity"])
    name_str = card_name or bl.text.strip()
    t.append(f"{name_str:<26}", style="bold" if is_cursor else "")

    if card:
        t.append(format_mana(card.mana_cost))
        type_short = card.type_line.split("\u2014")[0].strip()[:20]
        t.append(f"  {type_short}", style="dim")

    # The active sideboard plan's boarding for this deck card
    if plan_delta:
        t.append(f"  {plan_delta:+d}", style=_delta_style(plan_delta))

    # Render inline category
    category = buf.category_at(line_idx)
    if category:
        t.append(f"  @{category}", style=f"dim {COLORS['category']}")

    # Render inline tags
    tags = buf.tags_at(line_idx)
    if tags:
        tag_str = " ".join(f"#{tag}" for tag in sorted(tags))
        t.append(f"  {tag_str}", style=f"dim {COLORS['tag']}")

    # Render inline card comment
    comment = buf.comment_at(line_idx)
    if comment:
        t.append(f"  // {comment}", style="dim italic")

    if is_cursor:
        t.stylize(_CURSOR_STYLE)

    lines: list[Text] = [t]

    if is_cursor and card and auto_expand:
        lines.extend(_render_expansion(
            card, gutter_pad,
            price_source=price_source, currency_symbol=currency_symbol,
            show_prices=show_prices, width=width,
        ))

    return lines


def _render_expansion(
    card: Card,
    gutter_pad: Text | None = None,
    price_source: str = "usd",
    currency_symbol: str = "$",
    show_prices: bool = True,
    width: int | None = None,
) -> list[Text]:
    """Render expansion lines with proper word-wrapping to avoid broken indentation.

    `width` is the rendering widget's width; the terminal size is only a
    fallback for headless use (the widget may not span the terminal).
    """
    lines: list[Text] = []
    pad = gutter_pad.plain if gutter_pad else ""
    prefix = f"{pad} \u2502    "
    prefix_len = len(prefix)

    if width and width > 0:
        term_width = max(40, width - 2)
    else:
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
    if show_prices:
        price = card.prices.get(price_source)
        if price is not None:
            meta_parts.append(f"{currency_symbol}{price:.2f}")
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

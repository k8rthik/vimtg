"""Sort-key extraction for card lines — the single source of truth.

Shared by :sort and the layout regrouper so "order by cmc" means the
same thing everywhere. Every extractor returns a (numeric, string)
2-tuple so sorted() never compares mismatched shapes.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import re
from typing import Any

from vimtg.domain.card import Color, Rarity
from vimtg.domain.card_types import TYPE_ORDER, primary_type
from vimtg.domain.deck_lines import (
    CARD_PATTERN,
    CMD_PATTERN,
    MB_PATTERN,
    SB_PATTERN,
    parse_card_parts,
    split_inline_comment,
)
from vimtg.domain.tags import parse_inline_tags
from vimtg.editor.buffer import BufferLine

# Every field :sort (and the sort_order setting) accepts
SORT_FIELDS = frozenset({
    "name", "qty", "cmc", "type", "color", "tag", "category",
    "power", "toughness", "rarity", "price",
})

# Fields that need resolved card data (fall back to name without it)
CARD_DATA_FIELDS = frozenset({
    "cmc", "type", "color", "power", "toughness", "rarity", "price",
})

_COLOR_ORDER: dict[str, int] = {c.value: i for i, c in enumerate(Color)}
_RARITY_ORDER: dict[Rarity, int] = {r: i for i, r in enumerate(Rarity)}

# Missing/unresolved values sort after everything real
_MISSING = 9999.0

_LEADING_NUMBER = re.compile(r"^-?\d+")


def stat_to_float(stat: str | None) -> float | None:
    """Coerce a Scryfall power/toughness string to a sortable number.

    Handles plain numbers ('3'), stars ('*' → 0), and hybrids
    ('1+*' → 1). Returns None when there is no numeric content.
    """
    if stat is None or not stat.strip():
        return None
    if stat.strip() == "*":
        return 0.0
    m = _LEADING_NUMBER.match(stat.strip())
    return float(m.group(0)) if m else None


def extract_sort_key(
    line: BufferLine,
    sort_field: str,
    resolved_cards: dict[str, Any] | None = None,
    price_source: str = "usd",
) -> tuple[float, str]:
    """Extract a sort key from a card line based on the requested field."""
    text = line.text.strip()
    card_name = extract_card_name(text)
    card = resolved_cards.get(card_name) if resolved_cards else None
    fallback = card_name.lower()

    if sort_field == "qty":
        m = match_card_line(text)
        return (int(m.group(1)) if m else 0, fallback)

    if sort_field == "cmc":
        return (card.cmc if card is not None else _MISSING, fallback)

    if sort_field == "type":
        if card is None:
            return (99, fallback)
        ptype = primary_type(card.type_line)
        return (TYPE_ORDER.get(ptype, 99) if ptype else 99, fallback)

    if sort_field == "color":
        if card is None:
            return (99, fallback)
        colors = card.colors or []
        if not colors:
            return (99, fallback)
        if len(colors) > 1:
            return (10 + len(colors), fallback)
        color_val = (
            colors[0].value if hasattr(colors[0], "value")
            else str(colors[0])
        )
        return (_COLOR_ORDER.get(color_val, 98), fallback)

    if sort_field == "tag":
        # '#word' inside an inline comment is prose, not a tag
        tags = parse_inline_tags(split_inline_comment(text)[0])
        if not tags:
            return (1, fallback)  # untagged cards sort after tagged
        first_tag = sorted(tags)[0]
        return (0, first_tag + "|" + fallback)

    if sort_field == "category":
        m = match_card_line(text)
        category = parse_card_parts(m.group(2))[1] if m else ""
        if not category:
            return (1, fallback)  # uncategorized cards sort last
        return (0, category + "|" + fallback)

    if sort_field == "power":
        value = stat_to_float(card.power) if card is not None else None
        return (value if value is not None else _MISSING, fallback)

    if sort_field == "toughness":
        value = stat_to_float(card.toughness) if card is not None else None
        return (value if value is not None else _MISSING, fallback)

    if sort_field == "rarity":
        if card is None:
            return (_MISSING, fallback)
        return (_RARITY_ORDER.get(card.rarity, 99), fallback)

    if sort_field == "price":
        price = card.prices.get(price_source) if card is not None else None
        return (price if price is not None else _MISSING, fallback)

    # "name" — sort alphabetically, all at same numeric priority
    return (0, fallback)


def match_card_line(text: str):  # type: ignore[no-untyped-def]
    """Match a card line against the shared deck-line grammar."""
    for pattern in (SB_PATTERN, MB_PATTERN, CMD_PATTERN, CARD_PATTERN):
        m = pattern.match(text)
        if m:
            return m
    return None


def extract_card_name(text: str) -> str:
    """Extract the card name from a line, stripping all suffix tokens."""
    m = match_card_line(text)
    raw = m.group(2) if m else text
    return parse_card_parts(raw)[0]

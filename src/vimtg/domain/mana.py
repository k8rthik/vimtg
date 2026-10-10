"""Mana-cost parsing: symbols, split-card halves, mana value.

Scryfall writes a split card's cost as both halves joined by " // "
("{1}{R} // {1}{U}" for Fire // Ice); every helper here understands
that form.
"""

from __future__ import annotations

import re

from vimtg.domain.card import Color, color_from_symbol

_SYMBOL_RE = re.compile(r"\{([^}]+)\}")
_HALF_SEPARATOR = " // "


def cost_halves(mana_cost: str) -> tuple[str, ...]:
    """The cost of each half of a split card; a one-element tuple
    for an ordinary cost."""
    return tuple(part.strip() for part in mana_cost.split(_HALF_SEPARATOR))


def mana_symbols(mana_cost: str) -> list[str]:
    """Inner text of every {symbol}, upper-cased: '{2}{w/p}' -> ['2', 'W/P']."""
    return [s.upper() for s in _SYMBOL_RE.findall(mana_cost)]


def is_phyrexian(symbol: str) -> bool:
    """{W/P}, {G/U/P}: payable with 2 life instead of mana."""
    return "P" in symbol.split("/")[1:]


def is_hybrid(symbol: str) -> bool:
    """A hybrid symbol: {R/G}, {2/W}, {G/U/P} (Phyrexian hybrid).
    A plain Phyrexian symbol ({B/P}) is not hybrid."""
    parts = [p for p in symbol.split("/") if p != "P"]
    return len(parts) >= 2


def symbol_colors(symbol: str) -> tuple[Color, ...]:
    """Colours a symbol shows, WUBRG order ({R/G} -> R, G; {2/W} -> W)."""
    found = {
        c for part in symbol.split("/")
        if len(part) == 1 and (c := color_from_symbol(part)) is not None
    }
    return tuple(c for c in Color if c in found)


def _symbol_value(symbol: str) -> float:
    """Mana value of one symbol (Comprehensive Rules 202.1): numbers
    count as themselves, X/Y/Z as 0, half symbols as 0.5, a hybrid
    symbol as its largest component, anything else as 1."""
    if symbol.isdigit():
        return float(symbol)
    if symbol in ("X", "Y", "Z"):
        return 0.0
    if symbol.startswith("H") or symbol == "½":
        return 0.5
    if "/" in symbol:
        return max(_symbol_value(p) for p in symbol.split("/") if p != "P")
    return 1.0


def mana_value(mana_cost: str) -> float:
    """Mana value of a single cost ('{2}{R/G}' -> 3)."""
    return sum(_symbol_value(s) for s in mana_symbols(mana_cost))

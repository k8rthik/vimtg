"""Per-format deck construction rules — pure data, no I/O.

Each format's `name` doubles as the key into Card.legalities (the raw
Scryfall map), so legality lookups and rule lookups can never disagree
about what a format is called.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatRules:
    name: str
    min_deck_size: int = 60
    # Commander: mainboard + commander must be exactly this size
    exact_deck_size: int | None = None
    # 1 = singleton; basic lands are always exempt
    copy_limit: int = 4
    allows_sideboard: bool = True
    max_sideboard: int = 15
    # Implies legendary + color-identity checks
    requires_commander: bool = False


FORMAT_RULES: dict[str, FormatRules] = {
    "standard": FormatRules(name="standard"),
    "pioneer": FormatRules(name="pioneer"),
    "modern": FormatRules(name="modern"),
    "legacy": FormatRules(name="legacy"),
    "vintage": FormatRules(name="vintage"),
    "commander": FormatRules(
        name="commander",
        exact_deck_size=100,
        copy_limit=1,
        allows_sideboard=False,
        requires_commander=True,
    ),
    "brawl": FormatRules(
        name="brawl",
        copy_limit=1,
        allows_sideboard=False,
        requires_commander=True,
    ),
    "pauper": FormatRules(name="pauper"),
    "historic": FormatRules(name="historic"),
}


def get_format_rules(fmt: str) -> FormatRules | None:
    """Rules for a format name (case-insensitive); None for ''/unknown."""
    return FORMAT_RULES.get(fmt.strip().lower())


def known_formats() -> tuple[str, ...]:
    """Format names with configured legality rules, sorted."""
    return tuple(sorted(FORMAT_RULES))

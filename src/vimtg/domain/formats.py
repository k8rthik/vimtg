"""Per-format deck construction rules — pure data, no I/O.

Each format's `name` doubles as the key into Card.legalities (the raw
Scryfall map), so legality lookups and rule lookups can never disagree
about what a format is called.

Sources (rules as of 2026-10):
- 60/15/4 constructed (standard, pioneer, modern, legacy, vintage,
  historic, timeless, pauper): MTG Tournament Rules 100.2a / 100.4a,
  https://magic.wizards.com/en/formats ; Historic and Timeless pages
  there give the same 60-card minimum, 15-card sideboard, 4-of limit.
- Premodern: https://premodernmagic.com (60 min, 15 sideboard, 4-of).
- Penny Dreadful: https://pennydreadfulmagic.com (60 min, 15 sideboard,
  4-of); Scryfall's legalities key is "penny".
- Commander: Comprehensive Rules 903.5a-b — exactly 100 cards including
  the commander, singleton, no sideboard.
- Brawl (Scryfall "brawl", Arena's 100-card Brawl) and Standard Brawl
  ("standardbrawl", 60 cards): https://magic.wizards.com/en/formats/brawl
  — exact size including the commander, singleton, no sideboard.
- Oathbreaker: https://oathbreakermtg.org/rules/ — exactly 60 cards
  including the Oathbreaker and its Signature Spell, singleton.
- Pauper Commander ("paupercommander"): PDH Home Base rules,
  https://www.pdhhomebase.com — 100 cards, singleton, no sideboard.
- Duel Commander ("duel"): https://www.mtgdc.info — 100 cards
  including the commander, singleton, no sideboard.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatRules:
    name: str
    min_deck_size: int = 60
    # Commander-style: mainboard + command zone must be exactly this size
    exact_deck_size: int | None = None
    # 1 = singleton; basic lands are always exempt
    copy_limit: int = 4
    allows_sideboard: bool = True
    max_sideboard: int = 15
    # Implies commander-eligibility + color-identity checks
    requires_commander: bool = False


def _commander_style(name: str, size: int) -> FormatRules:
    return FormatRules(
        name=name,
        exact_deck_size=size,
        copy_limit=1,
        allows_sideboard=False,
        requires_commander=True,
    )


FORMAT_RULES: dict[str, FormatRules] = {
    "standard": FormatRules(name="standard"),
    "pioneer": FormatRules(name="pioneer"),
    "modern": FormatRules(name="modern"),
    "legacy": FormatRules(name="legacy"),
    "vintage": FormatRules(name="vintage"),
    "pauper": FormatRules(name="pauper"),
    "historic": FormatRules(name="historic"),
    "timeless": FormatRules(name="timeless"),
    "premodern": FormatRules(name="premodern"),
    "penny": FormatRules(name="penny"),
    "commander": _commander_style("commander", 100),
    "brawl": _commander_style("brawl", 100),
    "standardbrawl": _commander_style("standardbrawl", 60),
    "oathbreaker": _commander_style("oathbreaker", 60),
    "paupercommander": _commander_style("paupercommander", 100),
    "duel": _commander_style("duel", 100),
}


def get_format_rules(fmt: str) -> FormatRules | None:
    """Rules for a format name (case-insensitive); None for ''/unknown."""
    return FORMAT_RULES.get(fmt.strip().lower())


def known_formats() -> tuple[str, ...]:
    """Format names with configured legality rules, sorted."""
    return tuple(sorted(FORMAT_RULES))

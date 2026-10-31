"""Deck texts and read-back helpers shared by the deck-structure cases.

No tests live here. The helpers read what a user can see: the deck text
as the .deck parser reads it, the section header a card sits under, the
rows the deck view draws dimmed, and the status line.
"""

from __future__ import annotations

import re

from rich.text import Text

from tests.primitives.harness import DECK, Ed
from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.deck import DeckEntry, DeckSection
from vimtg.tui.widgets.deck_view import DeckView

# Rows of the canonical DECK (0-based; G takes row + 1).
GOBLIN_ROW = 7  # 4 Goblin Guide
EIDOLON_ROW = 8
BOLT_ROW = 12  # 4 Lightning Bolt
FIRE_ICE_ROW = 13
RIP_ROW = 20  # SB: 2 Rest in Peace

# Commander deck in block style. Goblin Guide leads; nothing in the
# sample data is legendary, so every zc draws the commander warning.
#  0 // Deck: Big        5     1 Goblin Guide        11     1 Bonecrusher..
#  1 // Format: commander 6 (blank)                  13     // Instant
#  4 CMD:                7 DCK:                      14     1 Lightning Bolt
#                        9     // Creature           17     30 Mountain
#                       10     1 Eidolon of the Great Revel
CMD_DECK = (
    "// Deck: Big\n// Format: commander\n// Tags:\n\n"
    "CMD:\n"
    "    1 Goblin Guide\n"
    "\n"
    "DCK:\n"
    "\n"
    "    // Creature\n"
    "    1 Eidolon of the Great Revel\n"
    "    1 Bonecrusher Giant // Stomp\n"
    "\n"
    "    // Instant\n"
    "    1 Lightning Bolt\n"
    "\n"
    "    // Land\n"
    "    30 Mountain\n"
)

# An empty companion block, a mainboard, and a maybeboard block.
#  4 CMP:   6 DCK:   7 4 Goblin Guide   8 4 Lightning Bolt   10 MB:   11 1 Lava Spike
MB_DECK = (
    "// Deck: Maybe\n// Format: modern\n// Tags:\n\n"
    "CMP:\n"
    "\n"
    "DCK:\n"
    "    4 Goblin Guide\n"
    "    4 Lightning Bolt\n"
    "\n"
    "MB:\n"
    "    1 Lava Spike\n"
)

# Prefix style throughout: no zone blocks.
#  4 // Creatures   5 4 Goblin Guide   7 // Instants   8 4 Lightning Bolt
#  10 SB: 2 Rest in Peace   11 MB: 1 Lava Spike
PREFIX_DECK = (
    "// Deck: Prefix\n// Format: modern\n// Tags:\n\n"
    "// Creatures\n"
    "4 Goblin Guide\n"
    "\n"
    "// Instants\n"
    "4 Lightning Bolt\n"
    "\n"
    "SB: 2 Rest in Peace\n"
    "MB: 1 Lava Spike\n"
)

# A category-grouped deck already in the canonical category layout
# (groups in cmc-then-name order, uncategorized last).
#  6 // @burn       7 4 Lava Spike  @burn        8 4 Lightning Bolt  @burn
#  10 // @threats  11 4 Goblin Guide  @threats  12 2 Eidolon ..  @threats
#  14 // Uncategorized  15 20 Mountain   17 SB:  18 2 Rest in Peace
CAT_DECK = (
    "// Deck: Cats\n// Format: modern\n// Tags: aggro\n\n"
    "DCK:\n"
    "\n"
    "    // @burn\n"
    "    4 Lava Spike  @burn\n"
    "    4 Lightning Bolt  @burn\n"
    "\n"
    "    // @threats\n"
    "    4 Goblin Guide  @threats\n"
    "    2 Eidolon of the Great Revel  @threats\n"
    "\n"
    "    // Uncategorized\n"
    "    20 Mountain\n"
    "\n"
    "SB:\n"
    "    2 Rest in Peace\n"
)

# DECK plus two sideboard plans.
#  22 VS: Tron  // grind   23 -2 Lightning Bolt   24 +2 Rest in Peace
#  26 VS: Control          27 -1 Fire // Ice
PLAN_DECK = DECK + (
    "\n"
    "VS: Tron  // grind\n"
    "    -2 Lightning Bolt\n"
    "    +2 Rest in Peace\n"
    "\n"
    "VS: Control\n"
    "    -1 Fire // Ice\n"
)
TRON_ROW = 22
CONTROL_ROW = 26

ONE_PLAN_DECK = DECK + "\nVS: Tron\n    -2 Lightning Bolt\n    +2 Rest in Peace\n"

_SECTIONS = {
    "main": DeckSection.MAIN,
    "side": DeckSection.SIDEBOARD,
    "maybe": DeckSection.MAYBEBOARD,
    "commander": DeckSection.COMMANDER,
    "companion": DeckSection.COMPANION,
}

_DETAIL_BAR = "\u2502"  # the bar in front of an expanded card's detail rows
_ZONE_HEADER = re.compile(r"^(DCK|SB|MB|CMD|CMP):$", re.IGNORECASE)


def zone(text: str, name: str) -> dict[str, int]:
    """Card name -> total copies in one zone, as the .deck parser reads it."""
    section = _SECTIONS[name]
    out: dict[str, int] = {}
    for e in parse_deck_text(text).entries:
        if e.section is section:
            out[e.card_name] = out.get(e.card_name, 0) + e.quantity
    return out


def entries_in(text: str, name: str) -> list[DeckEntry]:
    section = _SECTIONS[name]
    return [e for e in parse_deck_text(text).entries if e.section is section]


def entry(text: str, card: str, zone_name: str = "main") -> DeckEntry:
    found = [e for e in entries_in(text, zone_name) if e.card_name == card]
    assert len(found) == 1, f"{card} in {zone_name}: {found}"
    return found[0]


def card_signature(text: str) -> list[tuple[str, str, int, str]]:
    """Every entry as (zone, name, qty, category), order-free."""
    return sorted(
        (e.section.value, e.card_name, e.quantity, e.category)
        for e in parse_deck_text(text).entries
    )


def plan(text: str, matchup: str) -> dict[str, int]:
    """Card -> signed count (-N out, +N in) in one VS: plan."""
    for p in parse_deck_text(text).plans:
        if p.name == matchup:
            return {e.card_name: e.delta for e in p.entries}
    raise AssertionError(f"no plan {matchup!r}")


def plan_names(text: str) -> list[str]:
    return [p.name for p in parse_deck_text(text).plans]


def card_row(lines: list[str], card: str, *, start: int = 0) -> int:
    """Row of the first card line from `start` naming `card`."""
    pattern = re.compile(rf"^(?:[A-Za-z]+:\s*)?[+-]?\d+ {re.escape(card)}(?:\s|$)")
    for i in range(start, len(lines)):
        if pattern.match(lines[i].strip()):
            return i
    raise AssertionError(f"{card} not found")


def header_above(lines: list[str], card: str, *, start: int = 0) -> str:
    """The section or zone header the card's line sits under."""
    row = card_row(lines, card, start=start)
    for i in range(row - 1, -1, -1):
        text = lines[i].strip()
        if text.startswith("//") or _ZONE_HEADER.match(text):
            return text
    return ""


def _rendered(ed: Ed) -> Text:
    return ed.screen.query_one("#deck-view", DeckView).render()


def rendered_rows(ed: Ed) -> list[str]:
    return _rendered(ed).plain.split("\n")


def dimmed_rows(ed: Ed) -> list[str]:
    """The rendered deck-view rows, card details aside (those are always
    drawn dim), that are drawn dim from end to end."""
    text = _rendered(ed)
    out: list[str] = []
    start = 0
    for row in text.plain.split("\n"):
        end = start + len(row)
        if row.strip() and _DETAIL_BAR not in row and any(
            s.start <= start and s.end >= end and "dim" in str(s.style)
            for s in text.spans
        ):
            out.append(row)
        start = end + 1
    return out


def dimmed_cards(ed: Ed, cards: tuple[str, ...]) -> set[str]:
    """Which of `cards` the deck view draws dimmed."""
    rows = dimmed_rows(ed)
    return {c for c in cards if any(c in r for r in rows)}

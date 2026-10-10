"""Deck analytics — mana curve, color distribution, type breakdown, stats."""

from __future__ import annotations

import re
from dataclasses import dataclass

from vimtg.domain.card import Card, Color, color_from_symbol
from vimtg.domain.card_types import primary_type
from vimtg.domain.deck import Deck, DeckSection

# Zones whose cards are part of the deck you play: the commander is
# cast from the command zone, so it counts toward totals, curve, pips.
_PLAYED_SECTIONS = frozenset({DeckSection.MAIN, DeckSection.COMMANDER})

# Land-count hint: Frank Karsten's regression fits, "How Many Lands Do
# You Need in Your Deck? An Updated Analysis" (2022) for 60 cards and
# "How Many Lands Do You Need in Commander?" for 99+1. Both are
# lands = base + slope * average mana value of the nonland cards; the
# cheap card draw / ramp term is left out, so the hint errs high.
_KARSTEN_60_BASE = 19.59
_KARSTEN_60_SLOPE = 1.90
_KARSTEN_60_DECK = 60
_KARSTEN_EDH_BASE = 31.42
_KARSTEN_EDH_SLOPE = 3.13
_KARSTEN_EDH_MIN_DECK = 80  # decks this big use the Commander fit

# Basic land type -> the colour it taps for (fetch-land heuristic).
_BASIC_TYPE_COLORS: dict[str, Color] = {
    "plains": Color.WHITE,
    "island": Color.BLUE,
    "swamp": Color.BLACK,
    "mountain": Color.RED,
    "forest": Color.GREEN,
}
# What a land's search finds: the rest of the sentence, cut at the
# put-it-onto-the-battlefield clause ('a Forest card and a Plains card').
_SEARCH_CLAUSE = re.compile(r"search your library for ([^.]*?)(?:, put|, reveal|\.|$)")

# Commander Brackets (https://magic.wizards.com/en/formats/commander):
# Brackets 1-2 allow no Game Changers, Bracket 3 up to three, 4-5 any.
_BRACKET_3_MAX_GAME_CHANGERS = 3

# Colored sources needed to cast a card with N pips of one color on
# turn T reliably, in a 60-card deck (Frank Karsten's tables,
# simplified: turn = the card's CMC). Scaled by mainboard size.
_KARSTEN_SOURCE_TABLE: dict[int, dict[int, int]] = {
    1: {1: 14, 2: 13, 3: 12, 4: 11, 5: 10, 6: 9, 7: 8},
    2: {2: 20, 3: 18, 4: 16, 5: 15, 6: 14, 7: 13},
    3: {3: 23, 4: 20, 5: 19, 6: 18, 7: 16},
}
_KARSTEN_BASELINE_DECK = 60


@dataclass(frozen=True)
class ManaCurve:
    """CMC distribution. Key 7 means '7+'."""

    buckets: dict[int, int]

    def max_count(self) -> int:
        return max(self.buckets.values(), default=0)

    def total(self) -> int:
        return sum(self.buckets.values())


@dataclass(frozen=True)
class ColorDistribution:
    """Mana pip counts and per-card color counts."""

    pips: dict[Color, int]
    cards: dict[Color, int]
    colorless_count: int


@dataclass(frozen=True)
class TypeBreakdown:
    """Card counts by primary type."""

    counts: dict[str, int]

    def total_nonland(self) -> int:
        return sum(v for k, v in self.counts.items() if k != "Land")


@dataclass(frozen=True)
class DeckStats:
    """Aggregate statistics for a deck."""

    total_cards: int
    mainboard_count: int
    sideboard_count: int
    unique_cards: int
    average_cmc: float
    median_cmc: float
    land_count: int
    nonland_count: int
    mana_curve: ManaCurve
    color_distribution: ColorDistribution
    type_breakdown: TypeBreakdown
    # Total in `price_source` (the name predates other currencies)
    total_price_usd: float | None
    # Karsten land-count hint; None without resolved nonland cards
    recommended_lands: int | None
    commander_count: int = 0
    price_source: str = "usd"


@dataclass(frozen=True)
class ColorRequirement:
    """One color's mana-base health: pips asked vs sources available."""

    color: Color
    pips: int  # total pips of this color across nonland played cards
    sources: int  # lands that can produce it (see land_source_colors)
    needed: int  # Karsten-scaled sources for the deck's toughest card

    @property
    def satisfied(self) -> bool:
        return self.sources >= self.needed


@dataclass(frozen=True)
class ManaBaseCheck:
    """Per-color source counts vs requirements, WUBRG order."""

    requirements: tuple[ColorRequirement, ...]
    total_lands: int


@dataclass(frozen=True)
class BracketEstimate:
    """Commander bracket floor implied by the deck's Game Changers.

    Heuristic: only the Game Changer count is known; mass land
    denial, extra-turn chains, two-card combos, and intent (which the
    bracket definitions weigh most) can all put a deck higher.
    """

    game_changers: tuple[str, ...]  # names, deck order, deduplicated

    @property
    def count(self) -> int:
        return len(self.game_changers)

    @property
    def label(self) -> str:
        """'1-2', '3', or '4+' — the lowest bracket the deck fits."""
        if self.count == 0:
            return "1-2"
        if self.count <= _BRACKET_3_MAX_GAME_CHANGERS:
            return "3"
        return "4+"


def zone_counts(deck: Deck) -> dict[DeckSection, int]:
    """Card quantities per zone; every zone present (0 when empty)."""
    counts = {section: 0 for section in DeckSection}
    for entry in deck.entries:
        counts[entry.section] += entry.quantity
    return counts


def category_counts(deck: Deck) -> dict[str, int]:
    """Mainboard card quantities per @category ('' = uncategorized)."""
    counts: dict[str, int] = {}
    for entry in deck.entries:
        if entry.section != DeckSection.MAIN:
            continue
        counts[entry.category] = counts.get(entry.category, 0) + entry.quantity
    return counts


def _karsten_needed(pips: int, cmc: float, mainboard_count: int) -> int:
    """Sources needed for `pips` pips on turn=CMC, scaled to deck size."""
    row = _KARSTEN_SOURCE_TABLE[min(pips, 3)]
    turn = min(max(int(cmc), min(row)), max(row))
    return round(row[turn] * mainboard_count / _KARSTEN_BASELINE_DECK)


def _basic_colors(deck: Deck, resolved_cards: dict[str, Card]) -> set[Color]:
    """Colours the deck's basic lands tap for (what a 'basic land' fetch finds)."""
    found: set[Color] = set()
    for entry in deck.entries:
        if entry.section not in _PLAYED_SECTIONS:
            continue
        card = resolved_cards.get(entry.card_name)
        if card is not None and card.is_land and "Basic" in card.type_line:
            found.update(_produced_colors(card))
    return found


def _produced_colors(card: Card) -> set[Color]:
    """Colours a land taps for itself.

    Scryfall's produced_mana when present; otherwise (a database synced
    before produced_mana was stored) the land's basic types plus its
    colour identity, the old proxy.
    """
    if card.produced_mana:
        return {
            c for sym in card.produced_mana
            if (c := color_from_symbol(sym)) is not None
        }
    front = card.type_line.split("//")[0].lower()
    typed = {c for name, c in _BASIC_TYPE_COLORS.items() if name in front}
    # A land with no produced_mana that fetches (Arid Mesa, Evolving
    # Wilds) has an empty identity, so this adds nothing for it.
    return typed | set(card.color_identity)


def _fetch_colors(card: Card, basic_colors: set[Color]) -> set[Color]:
    """Colours a fetch land can find, from its oracle text.

    'Search your library for a Mountain or Plains card' -> R, W (the
    named basic land types). 'Search your library for a basic land
    card' (Evolving Wilds, Fabled Passage) -> the colours of the basic
    lands in this deck. Conservative: anything else finds nothing.
    """
    found: set[Color] = set()
    for clause in _SEARCH_CLAUSE.findall(card.oracle_text.lower()):
        named = {c for name, c in _BASIC_TYPE_COLORS.items() if name in clause}
        if named:
            found |= named
        elif "basic land" in clause:
            found |= basic_colors
    return found


def land_source_colors(card: Card, basic_colors: set[Color]) -> set[Color]:
    """Colours a land counts as a source for: what it produces plus
    what it can fetch. Command Tower and City of Brass list every
    colour in produced_mana; Arid Mesa produces nothing but fetches."""
    return _produced_colors(card) | _fetch_colors(card, basic_colors)


def compute_mana_base(
    deck: Deck, resolved_cards: dict[str, Card]
) -> ManaBaseCheck:
    """Colored sources vs pip requirements for the played cards.

    A land (by front face) counts as a source for every colour in
    land_source_colors. The per-colour requirement is the deck's most
    demanding card (commander included) under the Karsten table,
    scaled by mainboard size.
    """
    played = [e for e in deck.entries if e.section in _PLAYED_SECTIONS]
    mainboard_count = sum(
        e.quantity for e in played if e.section == DeckSection.MAIN
    )
    basic_colors = _basic_colors(deck, resolved_cards)
    pips_by_color: dict[Color, int] = {}
    needed_by_color: dict[Color, int] = {}
    sources_by_color: dict[Color, int] = {}
    total_lands = 0

    for entry in played:
        card = resolved_cards.get(entry.card_name)
        if card is None:
            continue
        if card.is_land:
            total_lands += entry.quantity
            for color in land_source_colors(card, basic_colors):
                sources_by_color[color] = (
                    sources_by_color.get(color, 0) + entry.quantity
                )
            continue
        for color, pips in count_mana_pips(card.mana_cost).items():
            pips_by_color[color] = (
                pips_by_color.get(color, 0) + pips * entry.quantity
            )
            needed = _karsten_needed(pips, card.cmc, mainboard_count)
            needed_by_color[color] = max(
                needed_by_color.get(color, 0), needed
            )

    requirements = tuple(
        ColorRequirement(
            color=color,
            pips=pips_by_color[color],
            sources=sources_by_color.get(color, 0),
            needed=needed_by_color.get(color, 0),
        )
        for color in Color
        if color in pips_by_color
    )
    return ManaBaseCheck(requirements=requirements, total_lands=total_lands)


def count_mana_pips(mana_cost: str) -> dict[Color, int]:
    """Count color pips in a mana cost string like '{2}{R}{R}'.

    A hybrid symbol is a pip of each of its colours ({R/G} -> R and G,
    {2/W} -> W); a Phyrexian symbol is a pip of its colour ({R/P} -> R),
    since paying life instead is not a mana source.
    """
    pips: dict[Color, int] = {}
    for symbol in re.findall(r"\{([^}]+)\}", mana_cost):
        for part in symbol.split("/"):
            color = color_from_symbol(part) if len(part) == 1 else None
            if color is not None:
                pips[color] = pips.get(color, 0) + 1
    return pips


def _classify_type(type_line: str) -> str | None:
    """Return the first matching primary type from the front face."""
    return primary_type(type_line)


def _compute_recommended_lands(avg_cmc: float, deck_size: int) -> int | None:
    """Karsten land-count hint for a deck of `deck_size` played cards.

    80+ cards use the Commander fit (99 + commander); smaller decks use
    the 60-card fit scaled by size (40-card Limited lands near 17).
    None when there is nothing to base it on.
    """
    if deck_size <= 0 or avg_cmc <= 0:
        return None
    if deck_size >= _KARSTEN_EDH_MIN_DECK:
        return round(_KARSTEN_EDH_BASE + _KARSTEN_EDH_SLOPE * avg_cmc)
    per_60 = _KARSTEN_60_BASE + _KARSTEN_60_SLOPE * avg_cmc
    return round(per_60 * deck_size / _KARSTEN_60_DECK)


def estimate_bracket(
    deck: Deck, resolved_cards: dict[str, Card]
) -> BracketEstimate:
    """Game Changers among the played cards (commander included)."""
    names: list[str] = []
    for entry in deck.entries:
        if entry.section not in _PLAYED_SECTIONS:
            continue
        card = resolved_cards.get(entry.card_name)
        if card is not None and card.game_changer and card.name not in names:
            names.append(card.name)
    return BracketEstimate(game_changers=tuple(names))


def is_commander_deck(deck: Deck) -> bool:
    """Whether Commander brackets apply: format 'commander', or no
    format with a card in the command zone."""
    fmt = deck.metadata.format.strip().lower()
    if fmt:
        return fmt == "commander"
    return any(e.section == DeckSection.COMMANDER for e in deck.entries)


def compute_stats(
    deck: Deck,
    resolved_cards: dict[str, Card],
    price_source: str = "usd",
) -> DeckStats:
    """Compute deck statistics over the played cards (mainboard and
    commander); the sideboard only adds to the total."""
    played_entries = [e for e in deck.entries if e.section in _PLAYED_SECTIONS]
    side_entries = [e for e in deck.entries if e.section == DeckSection.SIDEBOARD]
    mainboard_count = sum(
        e.quantity for e in played_entries if e.section == DeckSection.MAIN
    )
    commander_count = sum(
        e.quantity for e in played_entries if e.section == DeckSection.COMMANDER
    )
    sideboard_count = sum(e.quantity for e in side_entries)

    cmcs: list[float] = []
    curve: dict[int, int] = {i: 0 for i in range(8)}
    land_count = 0
    nonland_count = 0
    type_counts: dict[str, int] = {}
    total_pips: dict[Color, int] = {}
    card_colors: dict[Color, int] = {}
    colorless = 0
    total_price = 0.0
    has_price = False

    for entry in played_entries:
        card = resolved_cards.get(entry.card_name)
        if card is None:
            continue
        qty = entry.quantity

        if card.is_land:
            land_count += qty
        else:
            nonland_count += qty
            cmc_int = min(int(card.cmc), 7)
            curve[cmc_int] = curve.get(cmc_int, 0) + qty
            cmcs.extend(card.cmc for _ in range(qty))

        primary = _classify_type(card.type_line)
        if primary is not None:
            type_counts[primary] = type_counts.get(primary, 0) + qty

        pips = count_mana_pips(card.mana_cost)
        for color, count in pips.items():
            total_pips[color] = total_pips.get(color, 0) + count * qty

        if card.colors:
            for c in card.colors:
                card_colors[c] = card_colors.get(c, 0) + qty
        else:
            colorless += qty

        card_price = card.prices.get(price_source)
        if card_price is not None:
            total_price += card_price * qty
            has_price = True

    avg_cmc = sum(cmcs) / len(cmcs) if cmcs else 0.0
    sorted_cmcs = sorted(cmcs)
    median_cmc = sorted_cmcs[len(sorted_cmcs) // 2] if sorted_cmcs else 0.0

    return DeckStats(
        total_cards=mainboard_count + commander_count + sideboard_count,
        mainboard_count=mainboard_count,
        sideboard_count=sideboard_count,
        unique_cards=len(deck.unique_card_names()),
        average_cmc=round(avg_cmc, 2),
        median_cmc=median_cmc,
        land_count=land_count,
        nonland_count=nonland_count,
        mana_curve=ManaCurve(buckets=curve),
        color_distribution=ColorDistribution(
            pips=total_pips, cards=card_colors, colorless_count=colorless
        ),
        type_breakdown=TypeBreakdown(counts=type_counts),
        total_price_usd=round(total_price, 2) if has_price else None,
        recommended_lands=_compute_recommended_lands(
            avg_cmc, mainboard_count + commander_count
        ),
        commander_count=commander_count,
        price_source=price_source,
    )

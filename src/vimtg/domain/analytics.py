"""Deck analytics — mana curve, color distribution, type breakdown, stats."""

from __future__ import annotations

import re
from dataclasses import dataclass

from vimtg.domain.card import Card, Color, color_from_symbol
from vimtg.domain.card_types import primary_type
from vimtg.domain.deck import Deck, DeckSection

# Land-count heuristic (a simplified Frank Karsten model).
_DEFAULT_LAND_COUNT = 24  # fallback when curve data is unavailable
_KARSTEN_BASE_LANDS = 17.5  # baseline land count before curve adjustment
_KARSTEN_CMC_WEIGHT = 0.5  # how strongly average CMC raises the land count
_KARSTEN_DENSITY_SCALE = 2.5  # scales the nonland-density term
_MIN_LANDS = 20
_MAX_LANDS = 28

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
    total_price_usd: float | None
    recommended_lands: int


@dataclass(frozen=True)
class ColorRequirement:
    """One color's mana-base health: pips asked vs sources available."""

    color: Color
    pips: int  # total pips of this color across nonland mainboard cards
    sources: int  # lands whose color identity produces it
    needed: int  # Karsten-scaled sources for the deck's toughest card

    @property
    def satisfied(self) -> bool:
        return self.sources >= self.needed


@dataclass(frozen=True)
class ManaBaseCheck:
    """Per-color source counts vs requirements, WUBRG order."""

    requirements: tuple[ColorRequirement, ...]
    total_lands: int


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


def compute_mana_base(
    deck: Deck, resolved_cards: dict[str, Card]
) -> ManaBaseCheck:
    """Colored sources vs pip requirements for the mainboard.

    A land counts as a source for every color in its color identity —
    a proxy for produced mana that is right for nearly all lands.
    The per-color requirement is the deck's most demanding card under
    the Karsten table, scaled by mainboard size.
    """
    main_entries = [e for e in deck.entries if e.section == DeckSection.MAIN]
    mainboard_count = sum(e.quantity for e in main_entries)
    pips_by_color: dict[Color, int] = {}
    needed_by_color: dict[Color, int] = {}
    sources_by_color: dict[Color, int] = {}
    total_lands = 0

    for entry in main_entries:
        card = resolved_cards.get(entry.card_name)
        if card is None:
            continue
        if card.is_land:
            total_lands += entry.quantity
            for color in card.color_identity:
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
    """Count color pips in a mana cost string like '{2}{R}{R}'."""
    pips: dict[Color, int] = {}
    for symbol in re.findall(r"\{([^}]+)\}", mana_cost):
        color = color_from_symbol(symbol) if len(symbol) == 1 else None
        if color is not None:
            pips[color] = pips.get(color, 0) + 1
    return pips


def _classify_type(type_line: str) -> str | None:
    """Return the first matching primary type from the front face."""
    return primary_type(type_line)


def _compute_recommended_lands(
    avg_cmc: float, nonland_count: int, mainboard_count: int
) -> int:
    """Simplified Frank Karsten land recommendation."""
    if nonland_count == 0 or avg_cmc == 0:
        return _DEFAULT_LAND_COUNT
    denominator = max(mainboard_count, 1)
    density = nonland_count / denominator
    rec = round(
        _KARSTEN_BASE_LANDS
        + _KARSTEN_CMC_WEIGHT * avg_cmc * density * _KARSTEN_DENSITY_SCALE
    )
    return max(_MIN_LANDS, min(_MAX_LANDS, rec))


def compute_stats(
    deck: Deck,
    resolved_cards: dict[str, Card],
    price_source: str = "usd",
) -> DeckStats:
    """Compute all deck statistics from mainboard entries."""
    main_entries = [e for e in deck.entries if e.section == DeckSection.MAIN]
    side_entries = [e for e in deck.entries if e.section == DeckSection.SIDEBOARD]
    mainboard_count = sum(e.quantity for e in main_entries)
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

    for entry in main_entries:
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
        total_cards=mainboard_count + sideboard_count,
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
        recommended_lands=_compute_recommended_lands(avg_cmc, nonland_count, mainboard_count),
    )

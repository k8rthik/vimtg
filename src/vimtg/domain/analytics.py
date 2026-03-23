"""Deck analytics — mana curve, color distribution, type breakdown, stats."""

from __future__ import annotations

import re
from dataclasses import dataclass

from vimtg.domain.card import Card, Color
from vimtg.domain.deck import Deck, DeckSection


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


_COLOR_MAP: dict[str, Color] = {
    "W": Color.WHITE,
    "U": Color.BLUE,
    "B": Color.BLACK,
    "R": Color.RED,
    "G": Color.GREEN,
}

_PRIMARY_TYPES = (
    "Creature",
    "Instant",
    "Sorcery",
    "Enchantment",
    "Artifact",
    "Planeswalker",
    "Land",
)


def count_mana_pips(mana_cost: str) -> dict[Color, int]:
    """Count color pips in a mana cost string like '{2}{R}{R}'."""
    pips: dict[Color, int] = {}
    for symbol in re.findall(r"\{([^}]+)\}", mana_cost):
        color = _COLOR_MAP.get(symbol)
        if color is not None:
            pips[color] = pips.get(color, 0) + 1
    return pips


def _classify_type(type_line: str) -> str | None:
    """Return the first matching primary type from the front face."""
    front = type_line.split("—")[0].split("//")[0].strip()
    for t in _PRIMARY_TYPES:
        if t in front:
            return t
    return None


def _compute_recommended_lands(
    avg_cmc: float, nonland_count: int, mainboard_count: int
) -> int:
    """Simplified Frank Karsten land recommendation."""
    if nonland_count == 0 or avg_cmc == 0:
        return 24
    denominator = max(mainboard_count, 1)
    rec = round(17.5 + 0.5 * avg_cmc * nonland_count / denominator * 2.5)
    return max(20, min(28, rec))


def compute_stats(deck: Deck, resolved_cards: dict[str, Card]) -> DeckStats:
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

        if card.price_usd is not None:
            total_price += card.price_usd * qty
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

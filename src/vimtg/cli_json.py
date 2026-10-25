"""The JSON documents `vimtg <command> --json` prints.

Every shape the CLI emits is chosen here, once: commands build the
domain result and hand it to one of these pure functions. Each
document names itself in `"schema": "vimtg.<kind>/1"`; keys are
snake_case, numbers stay numbers and a value that is absent (no price,
no format) is null. A breaking change to a shape bumps its version.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, TypedDict

from vimtg.domain.deck import DeckSection

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from vimtg.domain.analytics import DeckStats
    from vimtg.domain.card import Card
    from vimtg.domain.collection import Ownership, OwnershipSummary
    from vimtg.domain.deck import Deck
    from vimtg.domain.validation import ValidationError, ValidationReport

# Zone keys are DeckSection values ("main", "sideboard", ...), in
# deck-list order, the same vocabulary in every document.
_ZONE_ORDER = (
    DeckSection.COMMANDER,
    DeckSection.COMPANION,
    DeckSection.MAIN,
    DeckSection.SIDEBOARD,
    DeckSection.MAYBEBOARD,
)


def dumps(doc: object) -> str:
    """The document as printed: indented, UTF-8 card names kept as is."""
    return json.dumps(doc, indent=2, ensure_ascii=False)


def _schema(kind: str) -> str:
    return f"vimtg.{kind}/1"


class ProblemJson(TypedDict):
    line: int | None
    level: str
    message: str
    code: str | None


class ValidationJson(TypedDict):
    schema: str
    file: str
    format: str | None
    ok: bool
    legality_checked: bool
    problems: list[ProblemJson]
    bracket: str | None


def _problem(problem: ValidationError) -> ProblemJson:
    return {
        "line": problem.line_number,
        "level": problem.level,
        "message": problem.message,
        "code": problem.code or None,
    }


def validation_doc(file: str, report: ValidationReport, ok: bool) -> ValidationJson:
    """`vimtg validate --json`: `ok` is what the exit code says (no
    errors, and no warnings either under --strict)."""
    return {
        "schema": _schema("validation"),
        "file": file,
        "format": report.fmt or None,
        "ok": ok,
        "legality_checked": report.legality_checked,
        "problems": [_problem(p) for p in report.problems],
        "bracket": report.bracket or None,
    }


class ZoneJson(TypedDict):
    cards: int
    unique: int


class StatsJson(TypedDict):
    total_cards: int
    average_cmc: float
    land_count: int
    nonland_count: int
    types: dict[str, int]
    mana_curve: list[int]  # index = mana value, the last bucket is 7+
    price: float | None
    price_source: str


class InfoJson(TypedDict):
    schema: str
    file: str
    name: str | None
    format: str | None
    format_source: str | None  # "deck", "default_format", or null
    zones: dict[str, ZoneJson]
    stats: StatsJson | None


def _stats(stats: DeckStats) -> StatsJson:
    curve = stats.mana_curve.buckets
    return {
        "total_cards": stats.total_cards,
        "average_cmc": stats.average_cmc,
        "land_count": stats.land_count,
        "nonland_count": stats.nonland_count,
        "types": {t.lower(): n for t, n in stats.type_breakdown.counts.items() if n},
        "mana_curve": [curve.get(mv, 0) for mv in range(8)],
        "price": stats.total_price_usd,
        "price_source": stats.price_source,
    }


def info_doc(
    file: str,
    deck: Deck,
    fmt: str,
    format_source: str,
    stats: DeckStats | None,
) -> InfoJson:
    """`vimtg info --json`: every zone's count, stats with card data.
    `fmt` and `format_source` are '' when the deck has no format."""
    zones: dict[str, ZoneJson] = {}
    for section in _ZONE_ORDER:
        entries = [e for e in deck.entries if e.section is section]
        zones[section.value] = {
            "cards": sum(e.quantity for e in entries),
            "unique": len({e.card_name for e in entries}),
        }
    return {
        "schema": _schema("info"),
        "file": file,
        "name": deck.metadata.name or None,
        "format": fmt or None,
        "format_source": format_source or None,
        "zones": zones,
        "stats": _stats(stats) if stats is not None else None,
    }


class PricesJson(TypedDict):
    usd: float | None
    usd_foil: float | None
    eur: float | None
    eur_foil: float | None
    tix: float | None


class CardJson(TypedDict):
    name: str
    mana_cost: str
    mana_value: float
    type_line: str
    colors: list[str]
    color_identity: list[str]
    set: str
    rarity: str
    oracle_text: str
    prices: PricesJson
    legal_formats: list[str]


class SearchJson(TypedDict):
    schema: str
    query: str
    cards: list[CardJson]


# Scryfall's legality statuses that allow the card in a deck
_PLAYABLE = frozenset({"legal", "restricted"})


def _card(card: Card) -> CardJson:
    p = card.prices
    return {
        "name": card.name,
        "mana_cost": card.mana_cost,
        "mana_value": card.cmc,
        "type_line": card.type_line,
        "colors": [c.value for c in card.colors],
        "color_identity": [c.value for c in card.color_identity],
        "set": card.set_code,
        "rarity": card.rarity.value,
        "oracle_text": card.full_oracle_text or card.oracle_text,
        "prices": {
            "usd": p.usd, "usd_foil": p.usd_foil, "eur": p.eur,
            "eur_foil": p.eur_foil, "tix": p.tix,
        },
        "legal_formats": sorted(
            f for f, status in card.legalities.items() if status in _PLAYABLE
        ),
    }


def search_doc(query: str, cards: Iterable[Card]) -> SearchJson:
    """`vimtg search --json`: the matching cards, best match first."""
    return {"schema": _schema("search"), "query": query, "cards": [_card(c) for c in cards]}


class MissingCardJson(TypedDict):
    name: str
    zone: str
    needed: int
    owned: int
    missing: int
    price: float | None  # one copy, in the totals' price_source


class MissingTotalsJson(TypedDict):
    needed: int
    owned: int
    missing: int
    missing_unique: int
    cost_to_complete: float | None
    unpriced_unique: int
    price_source: str


class MissingJson(TypedDict):
    schema: str
    file: str
    collection: str
    cards: list[MissingCardJson]
    totals: MissingTotalsJson


def missing_doc(
    file: str,
    collection: str,
    owns: Iterable[Ownership],
    resolved: Mapping[str, Card],
    summary: OwnershipSummary,
) -> MissingJson:
    """`vimtg missing --json`: each deck entry the collection cannot
    cover, in deck order, and the deck's totals. Names are the official
    ones when the card database knows the card."""
    cards: list[MissingCardJson] = []
    for own in owns:
        if not own.missing:
            continue
        card = resolved.get(own.entry.card_name)
        cards.append({
            "name": card.name if card is not None else own.entry.card_name,
            "zone": own.entry.section.value,
            "needed": own.needed,
            "owned": own.owned,
            "missing": own.missing,
            "price": card.prices.get(summary.price_source) if card is not None else None,
        })
    return {
        "schema": _schema("missing"),
        "file": file,
        "collection": collection,
        "cards": cards,
        "totals": {
            "needed": summary.needed_cards,
            "owned": summary.owned_cards,
            "missing": summary.missing_cards,
            "missing_unique": summary.missing_unique,
            "cost_to_complete": summary.cost_to_complete,
            "unpriced_unique": summary.unpriced_unique,
            "price_source": summary.price_source,
        },
    }

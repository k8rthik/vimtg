"""Row <-> Card conversion for SQLite storage."""

import json
import sqlite3

from vimtg.domain.card import Card, Prices, parse_colors, parse_rarity


def _safe_price(row: sqlite3.Row, key: str) -> float | None:
    """Safely get a price column, returning None if column doesn't exist."""
    try:
        value: float | None = row[key]
        return value
    except (IndexError, KeyError):
        return None


def _optional(row: sqlite3.Row, key: str) -> object:
    """A column added by a later migration, or None when absent."""
    try:
        value: object = row[key]
        return value
    except (IndexError, KeyError):
        return None


def row_to_card(row: sqlite3.Row) -> Card:
    """Convert a SQLite Row to a Card domain object."""
    colors = parse_colors(json.loads(row["colors"]))
    color_identity = parse_colors(json.loads(row["color_identity"]))

    legalities = json.loads(row["legalities"])
    keywords = tuple(json.loads(row["keywords"]))

    rarity = parse_rarity(row["rarity"])

    prices = Prices(
        usd=_safe_price(row, "price_usd"),
        usd_foil=_safe_price(row, "price_usd_foil"),
        eur=_safe_price(row, "price_eur"),
        eur_foil=_safe_price(row, "price_eur_foil"),
        tix=_safe_price(row, "price_tix"),
    )

    return Card(
        scryfall_id=row["scryfall_id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        cmc=row["cmc"],
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        colors=colors,
        color_identity=color_identity,
        power=row["power"],
        toughness=row["toughness"],
        set_code=row["set_code"],
        rarity=rarity,
        prices=prices,
        legalities=legalities,
        image_uri=row["image_uri"],
        layout=row["layout"],
        keywords=keywords,
        oracle_id=_str_or_none(_optional(row, "oracle_id")),
        produced_mana=tuple(json.loads(str(_optional(row, "produced_mana") or "[]"))),
        game_changer=bool(_optional(row, "game_changer")),
    )


def _str_or_none(value: object) -> str | None:
    return None if value is None else str(value)


def card_to_row(card: Card) -> tuple[object, ...]:
    """Serialize a Card to a tuple matching INSERT column order."""
    return (
        card.scryfall_id,
        card.name,
        card.mana_cost,
        card.cmc,
        card.type_line,
        card.oracle_text,
        json.dumps([c.value for c in card.colors]),
        json.dumps([c.value for c in card.color_identity]),
        card.power,
        card.toughness,
        card.set_code,
        card.rarity.value,
        card.prices.usd,
        card.prices.usd_foil,
        card.prices.eur,
        card.prices.eur_foil,
        card.prices.tix,
        json.dumps(card.legalities),
        card.image_uri,
        card.layout,
        json.dumps(list(card.keywords)),
        card.oracle_id,
        json.dumps(list(card.produced_mana)),
        int(card.game_changer),
    )

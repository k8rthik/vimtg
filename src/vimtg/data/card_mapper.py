"""Row <-> Card conversion for SQLite storage."""

import json
import sqlite3

from vimtg.domain.card import Card, Color, Rarity

_COLOR_MAP: dict[str, Color] = {c.value: c for c in Color}
_RARITY_MAP: dict[str, Rarity] = {r.value: r for r in Rarity}


def row_to_card(row: sqlite3.Row) -> Card:
    """Convert a SQLite Row to a Card domain object."""
    raw_colors = json.loads(row["colors"])
    colors = tuple(
        _COLOR_MAP[c] for c in raw_colors if c in _COLOR_MAP
    )

    raw_identity = json.loads(row["color_identity"])
    color_identity = tuple(
        _COLOR_MAP[c] for c in raw_identity if c in _COLOR_MAP
    )

    legalities = json.loads(row["legalities"])
    keywords = tuple(json.loads(row["keywords"]))

    rarity = _RARITY_MAP.get(row["rarity"], Rarity.SPECIAL)

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
        price_usd=row["price_usd"],
        legalities=legalities,
        image_uri=row["image_uri"],
        layout=row["layout"],
        keywords=keywords,
    )


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
        card.price_usd,
        json.dumps(card.legalities),
        card.image_uri,
        card.layout,
        json.dumps(list(card.keywords)),
    )

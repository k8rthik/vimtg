from dataclasses import dataclass
from enum import Enum


class Color(Enum):
    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"


class Rarity(Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    MYTHIC = "mythic"
    SPECIAL = "special"
    BONUS = "bonus"


_COLOR_MAP: dict[str, Color] = {c.value: c for c in Color}

_RARITY_MAP: dict[str, Rarity] = {r.value: r for r in Rarity}

_FACE_LAYOUTS = frozenset({"transform", "modal_dfc"})
_SPLIT_LAYOUTS = frozenset({"split"})
_ADVENTURE_LAYOUTS = frozenset({"adventure"})


def _parse_colors(raw: list[str]) -> tuple[Color, ...]:
    return tuple(_COLOR_MAP[c] for c in raw if c in _COLOR_MAP)


def _parse_rarity(raw: str) -> Rarity:
    return _RARITY_MAP.get(raw, Rarity.SPECIAL)


def _to_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class Prices:
    """All available price fields from Scryfall."""

    usd: float | None = None
    usd_foil: float | None = None
    eur: float | None = None
    eur_foil: float | None = None
    tix: float | None = None

    def get(self, source: str) -> float | None:
        """Get price by source key (usd, usd_foil, eur, eur_foil, tix)."""
        return getattr(self, source, None)


def _parse_prices(prices: dict[str, str | None] | None) -> Prices:
    if prices is None:
        return Prices()
    return Prices(
        usd=_to_float(prices.get("usd")),
        usd_foil=_to_float(prices.get("usd_foil")),
        eur=_to_float(prices.get("eur")),
        eur_foil=_to_float(prices.get("eur_foil")),
        tix=_to_float(prices.get("tix")),
    )


def _extract_image_uri(data: dict) -> str | None:
    image_uris = data.get("image_uris")
    if image_uris and isinstance(image_uris, dict):
        return image_uris.get("normal")
    faces = data.get("card_faces")
    if faces and isinstance(faces, list):
        face_uris = faces[0].get("image_uris")
        if face_uris and isinstance(face_uris, dict):
            return face_uris.get("normal")
    return None


def _build_from_face_layout(data: dict) -> dict:
    face = data["card_faces"][0]
    return {
        "mana_cost": face.get("mana_cost", ""),
        "oracle_text": face.get("oracle_text", ""),
        "power": face.get("power"),
        "toughness": face.get("toughness"),
    }


def _build_from_split_layout(data: dict) -> dict:
    faces = data["card_faces"]
    combined_text = "\n//\n".join(f.get("oracle_text", "") for f in faces)
    return {
        "mana_cost": faces[0].get("mana_cost", ""),
        "oracle_text": combined_text,
        "power": None,
        "toughness": None,
    }


def _build_from_adventure_layout(data: dict) -> dict:
    faces = data["card_faces"]
    creature_face = faces[0]
    combined_text = "\n//\n".join(f.get("oracle_text", "") for f in faces)
    return {
        "mana_cost": creature_face.get("mana_cost", ""),
        "oracle_text": combined_text,
        "power": creature_face.get("power"),
        "toughness": creature_face.get("toughness"),
    }


@dataclass(frozen=True)
class Card:
    scryfall_id: str
    name: str
    mana_cost: str
    cmc: float
    type_line: str
    oracle_text: str
    colors: tuple[Color, ...]
    color_identity: tuple[Color, ...]
    power: str | None
    toughness: str | None
    set_code: str
    rarity: Rarity
    prices: Prices
    legalities: dict[str, str]
    image_uri: str | None
    layout: str
    keywords: tuple[str, ...]

    @classmethod
    def from_scryfall(cls, data: dict) -> "Card":
        layout = data.get("layout", "normal")

        if layout in _FACE_LAYOUTS:
            face_fields = _build_from_face_layout(data)
        elif layout in _SPLIT_LAYOUTS:
            face_fields = _build_from_split_layout(data)
        elif layout in _ADVENTURE_LAYOUTS:
            face_fields = _build_from_adventure_layout(data)
        else:
            face_fields = {
                "mana_cost": data.get("mana_cost", ""),
                "oracle_text": data.get("oracle_text", ""),
                "power": data.get("power"),
                "toughness": data.get("toughness"),
            }

        return cls(
            scryfall_id=data["id"],
            name=data["name"],
            mana_cost=face_fields["mana_cost"],
            cmc=data.get("cmc", 0.0),
            type_line=data.get("type_line", ""),
            oracle_text=face_fields["oracle_text"],
            colors=_parse_colors(data.get("colors", [])),
            color_identity=_parse_colors(data.get("color_identity", [])),
            power=face_fields["power"],
            toughness=face_fields["toughness"],
            set_code=data.get("set", ""),
            rarity=_parse_rarity(data.get("rarity", "common")),
            prices=_parse_prices(data.get("prices")),
            legalities=dict(data.get("legalities", {})),
            image_uri=_extract_image_uri(data),
            layout=layout,
            keywords=tuple(data.get("keywords", [])),
        )

    @property
    def price_usd(self) -> float | None:
        """Backward compatibility — delegates to prices.usd."""
        return self.prices.usd

    @property
    def is_creature(self) -> bool:
        return "Creature" in self.type_line

    @property
    def is_land(self) -> bool:
        return "Land" in self.type_line

    @property
    def is_instant_or_sorcery(self) -> bool:
        return "Instant" in self.type_line or "Sorcery" in self.type_line

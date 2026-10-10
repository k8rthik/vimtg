"""Card-name normalisation — the one place that decides when two
spellings name the same card.

Scryfall stores multi-face cards (transform, modal DFC, split, adventure,
flip) under their full ``Front // Back`` name, while MTGO, Arena and most
decklists write just the front face ("Fable of the Mirror-Breaker"), a
single slash ("Fire/Ice"), or drop accents and the Æ ligature. Every
lookup goes through :func:`normalize_card_name` so those spellings meet
on one key, and :class:`CardMap` applies the same key to every ``get``
so callers can look a card up with whatever the user typed.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vimtg.domain.card import Card

FACE_SEPARATOR = " // "

# "Fire/Ice", "Fire//Ice", "Fire / Ice" and "Fire // Ice" are one card.
_SEPARATOR_RE = re.compile(r"\s*/{1,2}\s*")

# Characters NFKD leaves alone but that decklists spell interchangeably.
_FOLDS = str.maketrans(
    {
        "Æ": "Ae",
        "æ": "ae",
        "Œ": "Oe",
        "œ": "oe",
        "‘": "'",  # left single quote
        "’": "'",  # right single quote / typographic apostrophe
        "‐": "-",  # hyphen
        "‑": "-",  # non-breaking hyphen
    }
)

# Alias ranks: an exact full-name match beats a front face, which beats
# any other face, so a face name can never shadow another card's name.
RANK_FULL_NAME = 0
RANK_FRONT_FACE = 1
RANK_OTHER_FACE = 2


def normalize_card_name(name: str) -> str:
    """Canonical lookup key for a card name.

    Case-folded, accent-stripped, ligatures and typographic quotes
    folded, whitespace collapsed, and any ``/`` or ``//`` face separator
    spelled ``" // "``.
    """
    s = unicodedata.normalize("NFKD", name.translate(_FOLDS))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = _SEPARATOR_RE.sub(FACE_SEPARATOR, s.casefold())
    return " ".join(s.split())


def face_names(name: str) -> tuple[str, ...]:
    """The individual face names of a ``Front // Back`` card name.

    A single-faced name yields itself.
    """
    parts = tuple(p.strip() for p in name.split(FACE_SEPARATOR.strip()))
    return tuple(p for p in parts if p) or (name,)


def name_aliases(name: str) -> list[tuple[str, int]]:
    """Every normalised key a card with this full name resolves under.

    Returns ``(key, rank)`` pairs: the full name, then the front face,
    then each further face (split halves, adventure, DFC back).
    """
    full = normalize_card_name(name)
    aliases: list[tuple[str, int]] = [(full, RANK_FULL_NAME)]
    seen = {full}
    faces = face_names(name)
    if len(faces) > 1:
        for i, face in enumerate(faces):
            key = normalize_card_name(face)
            if key not in seen:
                seen.add(key)
                aliases.append((key, RANK_FRONT_FACE if i == 0 else RANK_OTHER_FACE))
    return aliases


class CardMap(dict[str, "Card"]):
    """Resolved cards keyed by :func:`normalize_card_name`.

    ``get``, ``[]`` and ``in`` normalise their key, so analytics, export
    and rendering can look a card up with the deck's own spelling
    ("lightning bolt", "Fire/Ice", "Fable of the Mirror-Breaker") and
    find the card the resolver matched. Being a ``dict`` keeps it a
    drop-in for every ``dict[str, Card]`` signature.
    """

    def __init__(
        self, items: Mapping[str, Card] | Iterable[tuple[str, Card]] = ()
    ) -> None:
        super().__init__()
        self.update(items)

    def __setitem__(self, key: str, value: Card) -> None:
        super().__setitem__(normalize_card_name(key), value)

    def __getitem__(self, key: str) -> Card:
        return super().__getitem__(normalize_card_name(key))

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and super().__contains__(normalize_card_name(key))

    def get(self, key: str, default: Card | None = None) -> Card | None:  # type: ignore[override]
        return super().get(normalize_card_name(key), default)

    def setdefault(self, key: str, default: Card) -> Card:
        return super().setdefault(normalize_card_name(key), default)

    def update(  # type: ignore[override]
        self, items: Mapping[str, Card] | Iterable[tuple[str, Card]] = ()
    ) -> None:
        pairs = items.items() if isinstance(items, Mapping) else items
        for key, card in pairs:
            self[key] = card

    def copy(self) -> CardMap:
        return CardMap(self)

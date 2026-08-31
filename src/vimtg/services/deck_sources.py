"""Online decklist sources: Moxfield, Archidekt, and ManaBox URLs.

Ported from cod-sync's source fetchers and adapted to vimtg's richer
deck model: where Cockatrice folds everything into main/side, vimtg
keeps commander, companion, and maybeboard as real zones, and an
Archidekt user category survives as the card's inline @category.

TUI-agnostic: no Textual imports. Network access is confined to
fetch_deck; the parse_* functions are pure and unit-testable.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from vimtg.domain.categories import CATEGORY_NAME_RE
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
from vimtg.domain.deck_lines import clamp_quantity

_TIMEOUT_SECONDS = 20.0
_USER_AGENT = "vimtg/0.1 (+local TUI deck editor)"

_MOXFIELD_API = "https://api2.moxfield.com/v3/decks/all/"
_MOXFIELD_ID_RE = re.compile(r"/decks/([A-Za-z0-9_-]+)")
_ARCHIDEKT_API = "https://archidekt.com/api/decks/"
_ARCHIDEKT_ID_RE = re.compile(r"/decks/(\d+)")

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class DeckSourceError(Exception):
    """A deck URL could not be fetched or understood."""


@dataclass(frozen=True)
class RemoteDeck:
    """A decklist fetched from an online source.

    `name` is the deck's title at the source ('' when unknown).
    """

    name: str
    deck: Deck


def is_deck_url(source: str) -> bool:
    """True for any http(s) URL — fetch_deck decides whether the host
    is supported, so a typo'd host errors instead of being read as a
    file path."""
    return bool(_URL_RE.match(source))


def fetch_deck(url: str) -> RemoteDeck:
    """Fetch and parse a deck from a supported deck-site URL.

    Raises DeckSourceError on an unsupported host, network failure, or
    a response that doesn't look like a deck.
    """
    host = (urlparse(url).hostname or "").lower()
    if "moxfield.com" in host:
        deck_id = _extract_id(url, _MOXFIELD_ID_RE, "Moxfield")
        return parse_moxfield(_get_json(url, _MOXFIELD_API + deck_id))
    if "archidekt.com" in host:
        deck_id = _extract_id(url, _ARCHIDEKT_ID_RE, "Archidekt")
        return parse_archidekt(_get_json(url, f"{_ARCHIDEKT_API}{deck_id}/"))
    if "manabox.app" in host:
        return parse_manabox_page(url, _get_text(url))
    raise DeckSourceError(
        f"Unsupported deck site: {host or '(no host)'} "
        "(moxfield.com, archidekt.com, manabox.app)"
    )


# ── HTTP plumbing ──────────────────────────────────────────────────


def _extract_id(url: str, pattern: re.Pattern[str], site: str) -> str:
    m = pattern.search(url)
    if not m:
        raise DeckSourceError(f"Could not extract {site} deck id from {url}")
    return m.group(1)


def _get(url: str, api_url: str, accept: str) -> httpx.Response:
    try:
        response = httpx.get(
            api_url,
            headers={"User-Agent": _USER_AGENT, "Accept": accept},
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        raise DeckSourceError(f"Deck request failed: {exc}") from exc
    if response.status_code != 200:
        raise DeckSourceError(
            f"Could not fetch deck from {url} (HTTP {response.status_code})"
        )
    return response


def _get_json(url: str, api_url: str) -> dict[str, Any]:
    response = _get(url, api_url, "application/json")
    try:
        data = response.json()
    except ValueError as exc:
        raise DeckSourceError(f"{url} returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise DeckSourceError(f"{url} returned an unexpected payload")
    return data


def _get_text(url: str) -> str:
    return _get(url, url, "text/html").text


# ── Shared deck assembly ───────────────────────────────────────────


def _entry(
    name: str, qty: int, section: DeckSection, category: str = ""
) -> DeckEntry:
    return DeckEntry(
        quantity=clamp_quantity(qty),
        card_name=name,
        section=section,
        category=category,
    )


def _deck(entries: list[DeckEntry]) -> Deck:
    return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())


def _category_slug(name: str) -> str:
    """Archidekt category name → vimtg category token ('' if unusable)."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-").lower()[:32]
    return slug if CATEGORY_NAME_RE.match(slug) else ""


# Archidekt's stock categories are type groupings, not user categories —
# importing them as @tokens would tag every card in a default deck.
_TYPE_CATEGORIES = frozenset({
    "creature", "creatures", "instant", "instants", "sorcery", "sorceries",
    "artifact", "artifacts", "enchantment", "enchantments", "planeswalker",
    "planeswalkers", "battle", "battles", "land", "lands", "other", "spell",
    "spells",
})


# ── Moxfield ───────────────────────────────────────────────────────

_MOXFIELD_BOARDS: dict[str, DeckSection] = {
    "commanders": DeckSection.COMMANDER,
    "companions": DeckSection.COMPANION,
    "mainboard": DeckSection.MAIN,
    "sideboard": DeckSection.SIDEBOARD,
    "maybeboard": DeckSection.MAYBEBOARD,
}


def parse_moxfield(data: dict[str, Any]) -> RemoteDeck:
    """Parse a Moxfield v3 API response (v2 top-level boards fall back)."""
    entries: list[DeckEntry] = []
    boards = data.get("boards")
    for board_name, section in _MOXFIELD_BOARDS.items():
        if isinstance(boards, dict):
            cards = (boards.get(board_name) or {}).get("cards") or {}
        else:
            cards = data.get(board_name) or {}
        if not isinstance(cards, dict):
            continue
        for raw in cards.values():
            qty = int(raw.get("quantity", 0))
            name = (raw.get("card") or {}).get("name")
            if qty <= 0 or not name:
                continue
            entries.append(_entry(name, qty, section))
    return RemoteDeck(name=(data.get("name") or "").strip(), deck=_deck(entries))


# ── Archidekt ──────────────────────────────────────────────────────

_ARCHIDEKT_ZONES: dict[str, DeckSection] = {
    "commander": DeckSection.COMMANDER,
    "companion": DeckSection.COMPANION,
    "sideboard": DeckSection.SIDEBOARD,
}


def parse_archidekt(data: dict[str, Any]) -> RemoteDeck:
    """Parse an Archidekt API response.

    A card's first category is its primary — the one that decides
    placement on Archidekt; the rest are labels and must not re-zone.
    `includedInDeck: false` categories are the maybeboard. A user-made
    primary category (not a zone, not a stock type grouping) becomes
    the card's inline @category.
    """
    excluded = {
        (cat.get("name") or "").strip().lower()
        for cat in data.get("categories") or []
        if not cat.get("includedInDeck", True)
    }
    entries: list[DeckEntry] = []
    for raw in data.get("cards") or []:
        qty = int(raw.get("quantity", 0))
        name = _archidekt_name(raw)
        if qty <= 0 or not name:
            continue
        categories = raw.get("categories") or []
        primary = (categories[0] or "").strip().lower() if categories else ""
        category = ""
        if primary in excluded:
            section = DeckSection.MAYBEBOARD
        elif primary in _ARCHIDEKT_ZONES:
            section = _ARCHIDEKT_ZONES[primary]
        else:
            section = DeckSection.MAIN
            if primary and primary not in _TYPE_CATEGORIES:
                category = _category_slug(primary)
        entries.append(_entry(name, qty, section, category))
    return RemoteDeck(name=(data.get("name") or "").strip(), deck=_deck(entries))


def _archidekt_name(raw: dict[str, Any]) -> str | None:
    card = raw.get("card") or {}
    oracle = card.get("oracleCard") or {}
    name = oracle.get("name") or card.get("displayName")
    return name if isinstance(name, str) else None


# ── ManaBox ────────────────────────────────────────────────────────

# The share page is server-rendered by Astro with the deck serialized
# into an <astro-island> props attribute (HTML-entity-encoded JSON in
# Astro's [type, value] tuple form). No public JSON API exists.
_ISLAND_RE = re.compile(
    r'<astro-island\b[^>]*\bcomponent-export="Main"[^>]*?\bprops="(?P<props>.*?)"\s',
    re.DOTALL,
)
_MANABOX_BOARDS: dict[int, DeckSection] = {
    0: DeckSection.COMMANDER,  # commander
    1: DeckSection.COMMANDER,  # oathbreaker
    2: DeckSection.COMMANDER,  # signature spell
    3: DeckSection.MAIN,
    4: DeckSection.SIDEBOARD,
    5: DeckSection.MAYBEBOARD,
}


def parse_manabox_page(url: str, page: str) -> RemoteDeck:
    """Extract and parse the deck embedded in a ManaBox share page."""
    m = _ISLAND_RE.search(page)
    if not m:
        raise DeckSourceError(f"No deck data found on page: {url}")
    try:
        props = json.loads(html.unescape(m.group("props")))
    except ValueError as exc:
        raise DeckSourceError(f"Could not parse deck JSON from {url}") from exc
    deck_data = _astro_decode(
        props.get("deck") if isinstance(props, dict) else None
    )
    if not isinstance(deck_data, dict) or not isinstance(
        deck_data.get("cards"), list
    ):
        raise DeckSourceError(f"Unexpected deck shape on page: {url}")
    entries: list[DeckEntry] = []
    for raw in deck_data["cards"]:
        if not isinstance(raw, dict):
            continue
        qty = int(raw.get("quantity") or 0)
        name = raw.get("name")
        if qty <= 0 or not name:
            continue
        board = raw.get("boardCategory")
        section = (
            _MANABOX_BOARDS.get(board, DeckSection.MAIN)
            if isinstance(board, int)
            else DeckSection.MAIN
        )
        entries.append(_entry(name, qty, section))
    return RemoteDeck(
        name=(deck_data.get("name") or "").strip(), deck=_deck(entries)
    )


def _astro_decode(node: Any) -> Any:
    """Decode Astro's [type, value] island serialization.

    Type 0 wraps a primitive or a dict of encoded values; type 1 wraps
    a list of encoded items. Unknown types return their payload so an
    unexpected one degrades rather than crashes.
    """
    if isinstance(node, list) and len(node) == 2 and isinstance(node[0], int):
        kind, payload = node
        if kind == 0 and isinstance(payload, dict):
            return {key: _astro_decode(value) for key, value in payload.items()}
        if kind == 1 and isinstance(payload, list):
            return [_astro_decode(item) for item in payload]
        return payload
    return node

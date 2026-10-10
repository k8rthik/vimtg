"""Online decklist sources: Moxfield, Archidekt, ManaBox, Deckstats,
TappedOut, and MTGGoldfish URLs.

The JSON-API fetchers are ported from cod-sync and adapted to vimtg's
richer deck model: where Cockatrice folds everything into main/side,
vimtg keeps commander, companion, and maybeboard as real zones, and an
Archidekt user category survives as the card's inline @category. The
text-shaped sources (Deckstats' api.php list, TappedOut's ?fmt=dec,
MTGGoldfish's /deck/download) share one tolerant decklist parser.

TUI-agnostic: no Textual imports. Network access is confined to
fetch_deck; the parse_* functions are pure and unit-testable.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

import httpx

from vimtg.domain.categories import CATEGORY_NAME_RE
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
from vimtg.domain.deck_lines import (
    clamp_quantity,
    strip_bom,
    strip_printing_suffix,
)

_TIMEOUT_SECONDS = 20.0
_USER_AGENT = "vimtg/0.1 (+local TUI deck editor)"

_MOXFIELD_API = "https://api2.moxfield.com/v3/decks/all/"
_MOXFIELD_ID_RE = re.compile(r"/decks/([A-Za-z0-9_-]+)")
_ARCHIDEKT_API = "https://archidekt.com/api/decks/"
_ARCHIDEKT_ID_RE = re.compile(r"/decks/(\d+)")
_DECKSTATS_API = (
    "https://deckstats.net/api.php?action=get_deck&id_type=saved"
    "&owner_id={owner}&id={deck}&response_type=list"
)
_DECKSTATS_ID_RE = re.compile(r"/decks/(\d+)/(\d+)")
_TAPPEDOUT_SLUG_RE = re.compile(r"/mtg-decks/([A-Za-z0-9_-]+)")
_GOLDFISH_ID_RE = re.compile(r"/deck/(?:download/)?(\d+)")

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class DeckSourceError(Exception):
    """A deck URL could not be fetched or understood."""


@dataclass(frozen=True)
class SkippedLine:
    """A decklist line that is neither a card, a header, nor a comment."""

    line_number: int
    text: str


@dataclass(frozen=True)
class RemoteDeck:
    """A decklist fetched from an online source.

    `name` is the deck's title at the source ('' when unknown).
    `skipped` lists text lines the parser could not read (text-shaped
    sources only).
    """

    name: str
    deck: Deck
    skipped: tuple[SkippedLine, ...] = ()


def stamped_deck(remote: RemoteDeck, url: str) -> Deck:
    """The fetched deck with provenance stamped into its metadata: the
    remote title becomes // Deck: and the URL is kept as // Source:."""
    from dataclasses import replace

    return replace(
        remote.deck,
        metadata=replace(remote.deck.metadata, name=remote.name, source=url),
    )


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
    if "deckstats.net" in host:
        return _fetch_deckstats(url)
    if "tappedout.net" in host:
        return _fetch_tappedout(url)
    if "mtggoldfish.com" in host:
        return _fetch_mtggoldfish(url)
    raise DeckSourceError(
        f"Unsupported deck site: {host or '(no host)'} "
        "(moxfield, archidekt, manabox, deckstats, tappedout, mtggoldfish)"
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
        if primary in excluded:
            section, category = DeckSection.MAYBEBOARD, ""
        else:
            section, category = archidekt_placement(primary)
        entries.append(_entry(name, qty, section, category))
    return RemoteDeck(name=(data.get("name") or "").strip(), deck=_deck(entries))


def primary_archidekt_category(categories: str) -> str:
    """First of a comma-separated Archidekt category list, lowercased,
    without '{top}'/'{noDeck}' flags: 'Commander{top},Legendary' ->
    'commander'."""
    first = categories.split(",", 1)[0]
    return re.sub(r"\{[^}]*\}", "", first).strip().lower()


def archidekt_placement(primary: str) -> tuple[DeckSection, str]:
    """(section, inline category) for an Archidekt primary category.

    Zone categories (Commander, Companion, Sideboard, Maybeboard) pick
    the section; a user-made category becomes the @category; stock
    type groupings are dropped.
    """
    if primary in _ARCHIDEKT_ZONES:
        return _ARCHIDEKT_ZONES[primary], ""
    if primary == "maybeboard":
        return DeckSection.MAYBEBOARD, ""
    if primary and primary not in _TYPE_CATEGORIES:
        return DeckSection.MAIN, _category_slug(primary)
    return DeckSection.MAIN, ""


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


# ── Text-shaped sources (Deckstats / TappedOut / MTGGoldfish) ──────
# Also the one parser behind file imports of MTGO .txt and Arena text.

# "4 Card" / "4x Card"; set/collector/finish suffixes are stripped from
# the name afterwards (strip_printing_suffix).
_TEXT_LINE_RE = re.compile(r"^(?P<qty>\d+)\s*[xX]?\s+(?P<name>.+?)\s*$")
_SB_PREFIX_RE = re.compile(r"^\s*SB:\s*", re.IGNORECASE)
# Deckstats marks the commander with a trailing "#!Commander" pragma.
_COMMANDER_PRAGMA_RE = re.compile(r"#!Commander\b", re.IGNORECASE)
# Archidekt's text export appends categories: "1x Sol Ring [Ramp]",
# "1x Atraxa (ONE) 196 [Commander{top}]".
_BRACKET_CATEGORIES_RE = re.compile(r"\s*\[(?P<cats>[^\[\]]*)\]\s*$")
# A trailing "(24)" count on a header line: "Sideboard (15)", "Lands (24)".
_HEADER_COUNT_RE = re.compile(r"\s*\(\d+\)\s*$")
_ZONE_HEADERS: dict[str, DeckSection] = {
    "deck": DeckSection.MAIN,
    "main": DeckSection.MAIN,
    "mainboard": DeckSection.MAIN,
    "maindeck": DeckSection.MAIN,
    "commander": DeckSection.COMMANDER,
    "commanders": DeckSection.COMMANDER,
    "companion": DeckSection.COMPANION,
    "companions": DeckSection.COMPANION,
    "sideboard": DeckSection.SIDEBOARD,
    "side": DeckSection.SIDEBOARD,
    "sb": DeckSection.SIDEBOARD,
    "maybeboard": DeckSection.MAYBEBOARD,
    "maybe": DeckSection.MAYBEBOARD,
}
# Arena exports open with "About" / "Name <deck name>" before "Deck".
_ABOUT_HEADER = "about"


@dataclass
class _TextCard:
    entry: DeckEntry
    group: int  # blank-line-separated card group, from 0


def parse_decklist_text(
    text: str, name: str, blank_splits: bool | None = False
) -> RemoteDeck:
    """Parse a plain-text decklist into a RemoteDeck.

    Understands "N Card" / "Nx Card" lines with optional set/collector/
    finish suffixes ("(SET) 123", "(PLST) ELD-115", "*F*"), SB:
    prefixes, Deckstats' "#!Commander" pragma and trailing "# ..."
    comments, Archidekt's "[Category]" suffixes, and zone headers as
    bare words or "//" comments ("Sideboard", "//Main", "Commander",
    "Sideboard (15)", ...). A header that is not a zone name
    (Deckstats' "//Lands (24)" groupings) is ignored. Arena's "About" /
    "Name ..." preamble supplies the deck name when `name` is empty.

    `blank_splits` decides what a blank line means: True treats the
    first blank line after a card as the main/sideboard divider
    (MTGGoldfish's download format); False makes blank lines neutral;
    None (auto, for files of unknown origin) splits only a headerless
    list made of exactly two blank-separated groups — the MTGO .txt
    shape — and leaves anything else alone.

    Lines that cannot be read are reported in RemoteDeck.skipped
    instead of being dropped silently.
    """
    cards: list[_TextCard] = []
    skipped: list[SkippedLine] = []
    section = DeckSection.MAIN
    group = 0
    saw_zone_marker = False
    in_about = False
    deck_name = name
    for line_number, raw in enumerate(strip_bom(text).splitlines(), start=1):
        line = raw.strip()
        if not line:
            if cards and cards[-1].group == group:
                group += 1
            if blank_splits is True and cards and section == DeckSection.MAIN:
                section = DeckSection.SIDEBOARD
            continue

        line_section = section
        if _SB_PREFIX_RE.match(line):
            line_section = DeckSection.SIDEBOARD
            saw_zone_marker = True
            line = _SB_PREFIX_RE.sub("", line, count=1)
        elif line.startswith(("//", "#")) or not line[0].isdigit():
            header = _HEADER_COUNT_RE.sub("", line.lstrip("/#").strip())
            header = header.rstrip(":").strip().lower()
            zone = _ZONE_HEADERS.get(header)
            if zone is not None:
                section = zone
                saw_zone_marker = True
                in_about = False
            elif header == _ABOUT_HEADER:
                in_about = True
            elif in_about and line.lower().startswith("name "):
                deck_name = deck_name or line[5:].strip()
            elif not (
                line.startswith(("//", "#")) or _HEADER_COUNT_RE.search(line)
            ):
                skipped.append(SkippedLine(line_number, raw.strip()))
            continue
        if _COMMANDER_PRAGMA_RE.search(line):
            line_section = DeckSection.COMMANDER
            saw_zone_marker = True
        # Strip trailing "# ..." comments (the #!Commander pragma too)
        line = line.split("#", 1)[0].rstrip()

        category = ""
        bracket = _BRACKET_CATEGORIES_RE.search(line)
        if bracket:
            line = line[: bracket.start()]
            bracket_section, category = archidekt_placement(
                primary_archidekt_category(bracket.group("cats"))
            )
            if bracket_section != DeckSection.MAIN:
                line_section = bracket_section
                saw_zone_marker = True

        m = _TEXT_LINE_RE.match(line)
        card_name = strip_printing_suffix(m.group("name")) if m else ""
        qty = int(m.group("qty")) if m else 0
        if not card_name or qty <= 0:
            skipped.append(SkippedLine(line_number, raw.strip()))
            continue
        cards.append(
            _TextCard(_entry(card_name, qty, line_section, category), group)
        )

    entries = [card.entry for card in cards]
    groups = {card.group for card in cards}
    if blank_splits is None and not saw_zone_marker and len(groups) == 2:
        side_group = max(groups)
        entries = [
            replace(card.entry, section=DeckSection.SIDEBOARD)
            if card.group == side_group
            else card.entry
            for card in cards
        ]
    return RemoteDeck(
        name=deck_name, deck=_deck(entries), skipped=tuple(skipped)
    )


def _fetch_deckstats(url: str) -> RemoteDeck:
    """Deckstats' api.php returns {'name': ..., 'list': <decklist text>}."""
    m = _DECKSTATS_ID_RE.search(url)
    if not m:
        raise DeckSourceError(f"Could not extract Deckstats deck id from {url}")
    data = _get_json(url, _DECKSTATS_API.format(owner=m.group(1), deck=m.group(2)))
    listing = data.get("list")
    if not isinstance(listing, str):
        raise DeckSourceError(f"{url} returned an unexpected payload")
    return parse_decklist_text(listing, name=(data.get("name") or "").strip())


def _fetch_tappedout(url: str) -> RemoteDeck:
    """TappedOut serves the raw .dec list at <deck-url>?fmt=dec."""
    m = _TAPPEDOUT_SLUG_RE.search(url)
    if not m:
        raise DeckSourceError(f"Could not extract TappedOut deck id from {url}")
    slug = m.group(1)
    text = _get_text(f"https://tappedout.net/mtg-decks/{slug}/?fmt=dec")
    return parse_decklist_text(text, name=slug.replace("-", " ").strip())


def _fetch_mtggoldfish(url: str) -> RemoteDeck:
    """MTGGoldfish serves plain text at /deck/download/<id> — mainboard,
    then a blank line, then the sideboard (no headers)."""
    m = _GOLDFISH_ID_RE.search(url)
    if not m:
        raise DeckSourceError(f"Could not extract MTGGoldfish deck id from {url}")
    text = _get_text(f"https://www.mtggoldfish.com/deck/download/{m.group(1)}")
    return parse_decklist_text(text, name="", blank_splits=True)

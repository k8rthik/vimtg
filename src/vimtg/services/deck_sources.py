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
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

import httpx

from vimtg import __version__
from vimtg.data.network_errors import describe_network_error
from vimtg.domain.card import Card
from vimtg.domain.categories import CATEGORY_NAME_RE
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
from vimtg.domain.deck_lines import (
    clamp_quantity,
    strip_bom,
    strip_printing_suffix,
)
from vimtg.domain.formats import known_formats, normalize_format
from vimtg.domain.tags import TAG_NAME_RE

_TIMEOUT_SECONDS = 20.0
_USER_AGENT = f"vimtg/{__version__} (+local TUI deck editor)"
# Text endpoints (TappedOut's ?fmt=dec, MTGGoldfish's download) answer
# plain text; share pages (ManaBox) answer HTML
_TEXT_ACCEPT = "text/plain, text/html;q=0.9, */*;q=0.5"

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

# Retry advice in network errors: the same words fit the editor and CLI
NETWORK_RETRY = "try again"

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
    sources only). `format` is the site's format for the deck as a
    vimtg format name ('' when unknown or not one vimtg checks).
    """

    name: str
    deck: Deck
    skipped: tuple[SkippedLine, ...] = ()
    format: str = ""


def stamped_deck(remote: RemoteDeck, url: str) -> Deck:
    """The fetched deck with provenance stamped into its metadata: the
    remote title becomes // Deck:, the site's format // Format:, and the
    URL is kept as // Source:."""
    return replace(
        remote.deck,
        metadata=replace(
            remote.deck.metadata,
            name=remote.name,
            format=remote.format or remote.deck.metadata.format,
            source=url,
        ),
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
    for domain, fetch in _SITES:
        if _on_domain(host, domain):
            return fetch(url)
    raise DeckSourceError(
        f"Unsupported deck site: {host or '(no host)'} "
        "(moxfield, archidekt, manabox, deckstats, tappedout, mtggoldfish)"
    )


def _on_domain(host: str, domain: str) -> bool:
    """True for the site itself or one of its subdomains, never for a
    look-alike such as 'moxfield.com.evil.example'."""
    return host == domain or host.endswith("." + domain)


def _fetch_moxfield(url: str) -> RemoteDeck:
    deck_id = _extract_id(url, _MOXFIELD_ID_RE, "Moxfield")
    return parse_moxfield(_get_json(url, _MOXFIELD_API + deck_id))


def _fetch_archidekt(url: str) -> RemoteDeck:
    deck_id = _extract_id(url, _ARCHIDEKT_ID_RE, "Archidekt")
    return parse_archidekt(_get_json(url, f"{_ARCHIDEKT_API}{deck_id}/"))


def _fetch_manabox(url: str) -> RemoteDeck:
    return parse_manabox_page(url, _get_text(url))


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
        host = urlparse(api_url).hostname or url
        raise DeckSourceError(
            describe_network_error(exc, service=host, host=host, retry=NETWORK_RETRY)
        ) from exc
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
    return _get(url, url, _TEXT_ACCEPT).text


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


# Deck-site format names that differ from vimtg's (Scryfall's) names
def site_format(value: object) -> str:
    """A deck site's format name as a vimtg format ('' when unknown):
    'Commander' -> 'commander', 'pauperEdh' -> 'paupercommander'. The
    aliases are formats.FORMAT_ALIASES, the same table a '// Format:'
    line goes through."""
    if not isinstance(value, str):
        return ""
    key = normalize_format(re.sub(r"[^a-z0-9]", "", value.lower()))
    return key if key in known_formats() else ""


def _json_int(value: object) -> int:
    """A quantity from a deck site's JSON as an int; 0 for null, a
    bool, or anything else that is not a whole number."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdecimal():
        return int(value.strip())
    return 0


# ── Moxfield ───────────────────────────────────────────────────────

_MOXFIELD_BOARDS: dict[str, DeckSection] = {
    "commanders": DeckSection.COMMANDER,
    # Oathbreaker's signature spell lives in the command zone too
    "signatureSpells": DeckSection.COMMANDER,
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
            qty = _json_int(raw.get("quantity"))
            name = (raw.get("card") or {}).get("name")
            if qty <= 0 or not name:
                continue
            entries.append(_entry(name, qty, section))
    return RemoteDeck(
        name=(data.get("name") or "").strip(),
        deck=_deck(entries),
        format=site_format(data.get("format")),
    )


# ── Archidekt ──────────────────────────────────────────────────────

# Archidekt's numeric deckFormat ids, for the formats vimtg checks
_ARCHIDEKT_FORMATS: dict[int, str] = {
    1: "standard",
    2: "modern",
    3: "commander",
    4: "legacy",
    5: "vintage",
    6: "pauper",
    10: "penny",
    12: "duel",
    13: "standardbrawl",
    14: "oathbreaker",
    15: "pioneer",
    16: "historic",
    17: "paupercommander",
    20: "brawl",
    22: "premodern",
    24: "timeless",
}

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
        qty = _json_int(raw.get("quantity"))
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
    raw_format = data.get("deckFormat")
    fmt = (
        _ARCHIDEKT_FORMATS.get(raw_format, "")
        if isinstance(raw_format, int) and not isinstance(raw_format, bool)
        else site_format(raw_format)
    )
    return RemoteDeck(
        name=(data.get("name") or "").strip(), deck=_deck(entries), format=fmt
    )


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
        qty = _json_int(raw.get("quantity"))
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
    "main deck": DeckSection.MAIN,
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


# Trailing vimtg-style tokens on a pasted line: "1 Sol Ring @ramp #fast"
# (any whitespace before each token, unlike the .deck grammar's two)
_TRAILING_TOKENS_RE = re.compile(
    r"(?:\s+[#@][a-zA-Z][a-zA-Z0-9-]{0,31})+\s*$"
)
_TOKEN_RE = re.compile(r"([#@])([a-zA-Z][a-zA-Z0-9-]{0,31})")

# A Commander list pasted without headers ("1 Kenrith" / blank / 99
# cards) has a one- or two-card group beside a ~100-card one
_COMMANDER_DECK_SIZES = range(95, 106)
# Brawl and Oathbreaker decks are 60 cards: there the small group must
# resolve to commander-eligible cards
_MIN_MAIN_WITH_ELIGIBLE_COMMANDER = 58

# Card-name resolver (the card database, when there is one)
CardLookup = Callable[[str], Card | None]

# Lowercase words a card name may hold ("Delver of Secrets"); any other
# lowercase word marks a bare line as prose, not a card name
_NAME_SMALL_WORDS = frozenset({
    "a", "an", "and", "as", "at", "by", "en", "for", "from", "in", "into",
    "of", "on", "or", "the", "to", "upon", "with", "//",
})


def _split_trailing_tokens(line: str) -> tuple[str, str, frozenset[str]]:
    """(line without tokens, @category, #tags) for a pasted card line."""
    m = _TRAILING_TOKENS_RE.search(line)
    if not m:
        return line, "", frozenset()
    category = ""
    tags: set[str] = set()
    for mark, body in _TOKEN_RE.findall(m.group(0)):
        if mark == "@":
            category = category or body.lower()
        elif TAG_NAME_RE.match(body):
            tags.add(body.lower())
    return line[: m.start()], category, frozenset(tags)


def _looks_like_card_name(line: str, lookup: CardLookup | None) -> bool:
    """True when a line with no quantity reads as a card name: the card
    database knows it, or it is title-cased like one ('Sol Ring',
    'Delver of Secrets') rather than prose ('not a card line')."""
    if lookup is not None and lookup(line) is not None:
        return True
    words = line.split()
    if not words or not words[0][:1].isupper():
        return False
    return all(
        not w[:1].isalpha() or w[:1].isupper() or w.lower() in _NAME_SMALL_WORDS
        for w in words
    )


def can_lead_deck(card: Card) -> bool:
    """A legendary creature or planeswalker, or a card whose text says
    it can be your commander — what a lone pasted card group is when it
    names one."""
    front = card.type_line.split("//")[0]
    if "Legendary" in front and ("Creature" in front or "Planeswalker" in front):
        return True
    return "can be your commander" in card.oracle_text.lower()


def _bare_name(line: str) -> str:
    """A quantity-less card line without its tokens, comment, category
    brackets and printing suffix: just the name to judge."""
    line = _split_trailing_tokens(line)[0].split("#", 1)[0]
    return strip_printing_suffix(_BRACKET_CATEGORIES_RE.sub("", line))


def _is_group_label(line: str) -> bool:
    """True for a line that labels a group of cards rather than naming
    one: 'Lands:', 'Creatures', 'Spells'."""
    word = line.strip().lower()
    return word.endswith(":") or word in _TYPE_CATEGORIES


def _command_zone_group(
    cards: list[_TextCard], lookup: CardLookup | None
) -> int | None:
    """The blank-separated group of a headerless two-group list (the
    caller checks there are exactly two) that is the command zone, or
    None when the list reads as main + sideboard.

    The small group must be one or two single copies, and the whole
    list ~100 cards (Commander), or every small-group card must be
    commander-eligible beside a 60-card-sized main group (Brawl,
    Oathbreaker). Whichever group comes first, commander-first
    (Moxfield) and commander-last lists both work.
    """
    totals: dict[int, int] = {}
    for card in cards:
        totals[card.group] = totals.get(card.group, 0) + card.entry.quantity
    small = min(totals, key=lambda g: (totals[g], g))
    big = max(totals, key=lambda g: (totals[g], -g))
    small_cards = [c.entry for c in cards if c.group == small]
    if totals[small] > 2 or any(e.quantity != 1 for e in small_cards):
        return None
    if totals[small] + totals[big] in _COMMANDER_DECK_SIZES:
        return small
    if lookup is None or totals[big] < _MIN_MAIN_WITH_ELIGIBLE_COMMANDER:
        return None
    leaders = [lookup(e.card_name) for e in small_cards]
    if all(card is not None and can_lead_deck(card) for card in leaders):
        return small
    return None


def parse_decklist_text(
    text: str,
    name: str,
    blank_splits: bool | None = False,
    lookup: CardLookup | None = None,
) -> RemoteDeck:
    """Parse a plain-text decklist into a RemoteDeck.

    Understands "N Card" / "Nx Card" lines with optional set/collector/
    finish suffixes ("(SET) 123", "(PLST) ELD-115", "*F*"), SB:
    prefixes, Deckstats' "#!Commander" pragma and trailing "# ..."
    comments, Archidekt's "[Category]" suffixes, trailing vimtg
    "@category" / "#tag" tokens, and zone headers as bare words or "//"
    comments ("Sideboard", "//Main", "Commander", "Sideboard (15)",
    ...). A header that is not a zone name (Deckstats' "//Lands (24)"
    groupings) is ignored. A line with no quantity ("Sol Ring") is one
    copy when it reads as a card name (see _looks_like_card_name).
    Arena's "About" / "Name ..." preamble supplies the deck name
    when `name` is empty.

    `blank_splits` decides what a blank line means: True treats the
    first blank line after a card as the main/sideboard divider
    (MTGGoldfish's download format); False makes blank lines neutral;
    None (auto, for files of unknown origin) splits only a headerless
    list made of exactly two blank-separated groups — the MTGO .txt
    shape — and leaves anything else alone. In that auto split a one-
    or two-card group beside a Commander-sized list is the command zone
    rather than a sideboard; `lookup` (card data, when available) also
    recognises a 60-card Brawl/Oathbreaker list by its leader.

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
                continue
            if header == _ABOUT_HEADER:
                in_about = True
                continue
            if in_about and line.lower().startswith("name "):
                deck_name = deck_name or line[5:].strip()
                continue
            if line.startswith(("//", "#")) or _HEADER_COUNT_RE.search(line):
                continue
            if _is_group_label(line) or not _looks_like_card_name(
                _bare_name(line), lookup
            ):
                skipped.append(SkippedLine(line_number, raw.strip()))
                continue
            # A bare card name ("Sol Ring") is one copy
            line = f"1 {line}"
        if _COMMANDER_PRAGMA_RE.search(line):
            line_section = DeckSection.COMMANDER
            saw_zone_marker = True
        line, token_category, tags = _split_trailing_tokens(line)
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
        category = category or token_category

        m = _TEXT_LINE_RE.match(line)
        card_name = strip_printing_suffix(m.group("name")) if m else ""
        qty = int(m.group("qty")) if m else 0
        if not card_name or qty <= 0:
            skipped.append(SkippedLine(line_number, raw.strip()))
            continue
        entry = replace(
            _entry(card_name, qty, line_section, category), tags=tags
        )
        cards.append(_TextCard(entry, group))

    entries = [card.entry for card in cards]
    groups = {card.group for card in cards}
    if blank_splits is None and not saw_zone_marker and len(groups) == 2:
        command_group = _command_zone_group(cards, lookup)
        if command_group is not None:
            moved, target = command_group, DeckSection.COMMANDER
        else:
            # Main + sideboard: the smaller group is the sideboard,
            # whichever comes first (a lone leader ahead of 59 cards
            # is not a 59-card sideboard); a tie keeps the second
            totals = {
                g: sum(c.entry.quantity for c in cards if c.group == g)
                for g in groups
            }
            moved = min(groups, key=lambda g: (totals[g], -g))
            target = DeckSection.SIDEBOARD
        entries = [
            replace(card.entry, section=target)
            if card.group == moved
            else card.entry
            for card in cards
        ]
        if command_group is not None:
            # The command zone reads first, as in a .deck file
            entries.sort(key=lambda e: e.section != DeckSection.COMMANDER)
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


# Each supported site's domain and fetcher, matched by _on_domain
_SITES: tuple[tuple[str, Callable[[str], RemoteDeck]], ...] = (
    ("moxfield.com", _fetch_moxfield),
    ("archidekt.com", _fetch_archidekt),
    ("manabox.app", _fetch_manabox),
    ("deckstats.net", _fetch_deckstats),
    ("tappedout.net", _fetch_tappedout),
    ("mtggoldfish.com", _fetch_mtggoldfish),
)

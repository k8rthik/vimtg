"""EDHREC recommendations client — commander pages, parsed and cached.

Fetches https://json.edhrec.com/pages/commanders/<slug>.json, validates
the payload into frozen dataclasses, and groups the site's cardlists
into per-card-type tabs for the recommendations panel.

TUI-agnostic: no Textual imports. Network access is confined to
EdhrecClient.fetch; everything else is pure and unit-testable.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

EDHREC_COMMANDER_URL = "https://json.edhrec.com/pages/commanders/{slug}.json"
EDHREC_CARD_URL = "https://edhrec.com/commanders/{slug}"
USER_AGENT = "vimtg/0.1.0"
TIMEOUT_SECONDS = 30
CACHE_MAX_AGE_DAYS = 7

# Display tabs, each merging one or more EDHREC cardlist tags. "Top"
# keeps the site's curated lists first; the rest follow the deck's own
# type-section order. Tabs whose source lists are absent are dropped.
TAB_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Top", ("highsynergycards", "topcards", "gamechangers", "newcards")),
    ("Creatures", ("creatures",)),
    ("Instants", ("instants",)),
    ("Sorceries", ("sorceries",)),
    ("Artifacts", ("utilityartifacts", "manaartifacts")),
    ("Enchantments", ("enchantments",)),
    ("Planeswalkers", ("planeswalkers",)),
    ("Battles", ("battles",)),
    ("Lands", ("utilitylands", "lands")),
)


class EdhrecError(Exception):
    """EDHREC page could not be fetched or understood."""


@dataclass(frozen=True)
class EdhrecCard:
    """One recommended card from an EDHREC cardlist."""

    name: str
    num_decks: int
    potential_decks: int
    synergy: float

    @property
    def inclusion_pct(self) -> float:
        """Share of eligible decks running this card, in percent.

        Clamped to [0, 100] — the site's counters occasionally disagree.
        """
        if self.potential_decks <= 0:
            return 0.0
        return min(100.0, max(0.0, 100.0 * self.num_decks / self.potential_decks))


@dataclass(frozen=True)
class EdhrecTab:
    """A display tab: a label and its merged, deduplicated cards."""

    label: str
    cards: tuple[EdhrecCard, ...]


@dataclass(frozen=True)
class EdhrecPage:
    """A parsed commander page, ready for the recommendations panel."""

    commander: str
    tabs: tuple[EdhrecTab, ...]


def commander_slug(names: Sequence[str]) -> str:
    """EDHREC URL slug for one commander or a partner pair.

    Site convention: lowercase, accents folded to ASCII, punctuation
    dropped, spaces hyphenated; partner pairs join both slugs with a
    hyphen. Split/double-faced names use the front face only.
    """
    parts = [
        slug for name in names if (slug := _slugify_one(name))
    ]
    if not parts:
        raise EdhrecError("No commander name to look up")
    return "-".join(parts)


# Letters NFKD cannot decompose to ASCII — fold them explicitly so
# 'Ætherling' becomes 'aetherling', not 'therling'.
_SPECIAL_LETTERS = str.maketrans({
    "Æ": "Ae", "æ": "ae", "Œ": "Oe", "œ": "oe",
    "ß": "ss", "Ø": "O", "ø": "o", "Đ": "D", "đ": "d",
})


def _slugify_one(name: str) -> str:
    front_face = name.split("//")[0].translate(_SPECIAL_LETTERS)
    folded = unicodedata.normalize("NFKD", front_face)
    ascii_name = folded.encode("ascii", "ignore").decode("ascii")
    # Apostrophes vanish entirely (K'rrik → krrik); any other run of
    # non-alphanumerics becomes a single hyphen.
    no_apostrophes = re.sub(r"['’]", "", ascii_name.lower())
    hyphenated = re.sub(r"[^a-z0-9]+", "-", no_apostrophes)
    return hyphenated.strip("-")


def parse_page(data: object, commander_fallback: str = "") -> EdhrecPage:
    """Validate a raw EDHREC JSON payload into an EdhrecPage.

    Malformed individual entries are skipped; a payload with no usable
    cardlists at all raises EdhrecError (never trust external data).
    """
    if not isinstance(data, dict):
        raise EdhrecError("Unexpected EDHREC response (not a JSON object)")
    container = data.get("container")
    json_dict = container.get("json_dict") if isinstance(container, dict) else None
    cardlists = json_dict.get("cardlists") if isinstance(json_dict, dict) else None
    if not isinstance(cardlists, list):
        raise EdhrecError("EDHREC response has no card lists")

    lists: dict[str, tuple[EdhrecCard, ...]] = {}
    for entry in cardlists:
        parsed = _parse_cardlist(entry)
        if parsed is not None:
            tag, cards = parsed
            lists[tag] = cards

    tabs = build_tabs(lists)
    if not tabs:
        raise EdhrecError("EDHREC response has no usable card lists")

    commander = commander_fallback
    if isinstance(container, dict) and isinstance(container.get("title"), str):
        commander = container["title"] or commander
    return EdhrecPage(commander=commander, tabs=tabs)


def _parse_cardlist(entry: object) -> tuple[str, tuple[EdhrecCard, ...]] | None:
    """One cardlist → (tag, cards), or None when the entry is malformed."""
    if not isinstance(entry, dict):
        return None
    tag = entry.get("tag")
    views = entry.get("cardviews")
    if not isinstance(tag, str) or not isinstance(views, list):
        return None
    cards = tuple(
        card for view in views if (card := _parse_cardview(view)) is not None
    )
    return tag, cards


def _parse_cardview(view: object) -> EdhrecCard | None:
    if not isinstance(view, dict):
        return None
    name = view.get("name")
    if not isinstance(name, str) or not name:
        return None
    return EdhrecCard(
        name=name,
        num_decks=_as_int(view.get("num_decks")),
        potential_decks=_as_int(view.get("potential_decks")),
        synergy=_as_float(view.get("synergy")),
    )


def _as_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, value)
    return 0


def _as_float(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def build_tabs(
    lists: dict[str, tuple[EdhrecCard, ...]],
) -> tuple[EdhrecTab, ...]:
    """Merge raw EDHREC cardlists into TAB_SPECS display tabs.

    Merging preserves each source list's order (the site already ranks
    within a list) and deduplicates by card name, first occurrence wins.
    Empty tabs are dropped.
    """
    tabs: list[EdhrecTab] = []
    for label, tags in TAB_SPECS:
        seen: set[str] = set()
        merged: list[EdhrecCard] = []
        for tag in tags:
            for card in lists.get(tag, ()):
                if card.name.lower() not in seen:
                    seen.add(card.name.lower())
                    merged.append(card)
        if merged:
            tabs.append(EdhrecTab(label=label, cards=tuple(merged)))
    return tuple(tabs)


class EdhrecClient:
    """Fetches commander pages with a silent on-disk JSON cache."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_age_days: int = CACHE_MAX_AGE_DAYS,
    ) -> None:
        self._cache_dir = cache_dir
        self._max_age_seconds = max_age_days * 86400

    def fetch(self, commanders: Sequence[str]) -> EdhrecPage:
        """Return the parsed page for the given commander(s).

        Raises EdhrecError on network failure, a missing page, or an
        unusable payload. Cache I/O errors degrade silently to a fetch.
        """
        slug = commander_slug(commanders)
        fallback = " + ".join(n for n in commanders if n.strip())
        data = self._read_cache(slug)
        if data is None:
            data = self._fetch_remote(slug, fallback)
            page = parse_page(data, commander_fallback=fallback)
            # Cache only a payload that parsed — a 200 with an unusable
            # body must not poison the cache and replay the failure
            self._write_cache(slug, data)
            return page
        return parse_page(data, commander_fallback=fallback)

    def _fetch_remote(self, slug: str, display_name: str) -> object:
        url = EDHREC_COMMANDER_URL.format(slug=slug)
        try:
            response = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            raise EdhrecError(f"EDHREC request failed: {exc}") from exc
        if response.status_code != 200:
            raise EdhrecError(
                f"No EDHREC page for {display_name or slug} "
                f"(HTTP {response.status_code})"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise EdhrecError("EDHREC returned invalid JSON") from exc

    def _cache_path(self, slug: str) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / "edhrec" / f"{slug}.json"

    def _read_cache(self, slug: str) -> object | None:
        path = self._cache_path(slug)
        if path is None:
            return None
        try:
            if time.time() - path.stat().st_mtime > self._max_age_seconds:
                return None
            data: object = json.loads(path.read_text(encoding="utf-8"))
            return data
        except (OSError, ValueError):
            return None

    def _write_cache(self, slug: str, data: object) -> None:
        path = self._cache_path(slug)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        except (OSError, TypeError, ValueError):
            pass  # cache is best-effort; the fetch already succeeded

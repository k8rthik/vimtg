"""Commander Spellbook combo lookups: what the deck already combos into,
and which combos are one card away.

POSTs the deck to https://backend.commanderspellbook.com/find-my-combos
(one request per lookup; the response is one object, never paginated),
validates the reply into frozen dataclasses, and caches the parsed
report on disk for seven days, keyed by the deck's cards.

TUI-agnostic: no Textual imports. Network access is confined to
SpellbookClient._fetch_remote; everything else is pure.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import httpx

from vimtg import __version__
from vimtg.data.network_errors import describe_network_error
from vimtg.domain.deck import Deck, DeckSection

FIND_MY_COMBOS_URL = "https://backend.commanderspellbook.com/find-my-combos"
COMBO_PAGE_URL = "https://commanderspellbook.com/combo/{id}/"
SITE_URL = "https://commanderspellbook.com"
SERVICE = "Commander Spellbook"
USER_AGENT = f"vimtg/{__version__}"
TIMEOUT_SECONDS = 30
CACHE_MAX_AGE_DAYS = 7
OPT_OUT_ENV = "VIMTG_NO_SPELLBOOK"
# Read a recorded find-my-combos response from this file instead of
# asking the service (the offline verify sandbox). Every report it
# produces says so in its note, and it never touches the cache.
FIXTURE_ENV = "VIMTG_SPELLBOOK_FIXTURE"

_CACHE_VERSION = 1


class SpellbookError(Exception):
    """Combos could not be looked up or understood."""


class _UnreachableError(SpellbookError):
    """No usable answer: offline, timed out, rate-limited, or down."""

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class Combo:
    """One combo: the cards it uses and what it produces. `missing` is
    the cards it uses that the deck does not hold."""

    id: str
    cards: tuple[str, ...]
    produces: tuple[str, ...]
    identity: str
    description: str
    mana_needed: str
    popularity: int
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComboReport:
    """The combos a deck contains, and those one card away from it."""

    included: tuple[Combo, ...]
    one_away: tuple[Combo, ...]
    note: str = ""  # e.g. "cached 9 days ago (offline)"; '' for a fresh report


@dataclass(frozen=True)
class DeckQuery:
    """What the service is told about a deck: per-zone card counts."""

    main: tuple[tuple[str, int], ...]
    commanders: tuple[tuple[str, int], ...]

    @property
    def names(self) -> frozenset[str]:
        return frozenset(name for name, _qty in self.main + self.commanders)

    def payload(self) -> dict[str, list[dict[str, object]]]:
        return {
            "main": [{"card": n, "quantity": q} for n, q in self.main],
            "commanders": [{"card": n, "quantity": q} for n, q in self.commanders],
        }

    def cache_key(self) -> str:
        rows = sorted(
            [("main", n, q) for n, q in self.main]
            + [("commanders", n, q) for n, q in self.commanders]
        )
        return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()[:24]


def deck_query(deck: Deck) -> DeckQuery:
    """The deck's playable cards: the command zone as commanders; the
    mainboard and companion as main. Sideboard and maybeboard are left
    out, since they are not in the deck."""

    def totals(sections: Iterable[DeckSection]) -> tuple[tuple[str, int], ...]:
        counts: dict[str, int] = {}
        for entry in deck.entries:
            if entry.section in sections and entry.quantity > 0:
                counts[entry.card_name] = counts.get(entry.card_name, 0) + entry.quantity
        return tuple(sorted(counts.items()))

    return DeckQuery(
        main=totals((DeckSection.MAIN, DeckSection.COMPANION)),
        commanders=totals((DeckSection.COMMANDER,)),
    )


def combo_url(combo_id: str) -> str:
    """The combo's page on commanderspellbook.com."""
    return COMBO_PAGE_URL.format(id=combo_id)


def _name_keys(name: str) -> tuple[str, str]:
    """A name and its front face, case-folded: a deck may list a
    double-faced card by its front face alone."""
    folded = name.casefold().strip()
    return folded, folded.split(" // ")[0]


def parse_report(data: object, deck_names: frozenset[str]) -> ComboReport:
    """Validate a find-my-combos response into a ComboReport.

    `one_away` is the almostIncluded bucket narrowed to combos missing
    exactly one of the deck's cards; the buckets that need other colours
    or another commander are dropped. Both lists are sorted by
    popularity. Malformed combos are skipped; a reply with no results
    object raises SpellbookError.
    """
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, dict):
        raise SpellbookError(f"Unexpected {SERVICE} response (no results)")
    held = {key for name in deck_names for key in _name_keys(name)}

    def bucket(key: str) -> list[Combo]:
        raw = results.get(key)
        combos = (_parse_combo(c, held) for c in (raw if isinstance(raw, list) else ()))
        return [c for c in combos if c is not None]

    included = [replace(c, missing=()) for c in bucket("included")]
    one_away = [c for c in bucket("almostIncluded") if len(c.missing) == 1]
    return ComboReport(included=_by_popularity(included), one_away=_by_popularity(one_away))


def _by_popularity(combos: list[Combo]) -> tuple[Combo, ...]:
    return tuple(sorted(combos, key=lambda c: (-c.popularity, c.id)))


def _parse_combo(raw: object, held: set[str]) -> Combo | None:
    if not isinstance(raw, dict):
        return None
    combo_id = raw.get("id")
    cards = _names(raw.get("uses"), "card")
    if not isinstance(combo_id, str) or not combo_id or not cards:
        return None
    missing = tuple(n for n in cards if not held.intersection(_name_keys(n)))
    popularity = raw.get("popularity")
    return Combo(
        id=combo_id,
        cards=cards,
        produces=_names(raw.get("produces"), "feature"),
        identity=_text(raw.get("identity")),
        description=_text(raw.get("description")),
        mana_needed=_text(raw.get("manaNeeded")),
        popularity=popularity if isinstance(popularity, int) and popularity > 0 else 0,
        missing=missing,
    )


def _names(entries: object, key: str) -> tuple[str, ...]:
    """The `name` of each entry's `key` object: uses → card, produces → feature."""
    if not isinstance(entries, list):
        return ()
    names: list[str] = []
    for entry in entries:
        inner = entry.get(key) if isinstance(entry, dict) else None
        name = inner.get("name") if isinstance(inner, dict) else None
        if isinstance(name, str) and name:
            names.append(name)
    return tuple(names)


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


class SpellbookClient:
    """Finds a deck's combos, with a silent on-disk cache per card list."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_age_days: int = CACHE_MAX_AGE_DAYS,
    ) -> None:
        self._cache_dir = cache_dir
        self._max_age_seconds = max_age_days * 86400

    def find(self, deck: Deck) -> ComboReport:
        """The deck's combos and its one-card-away combos.

        Raises SpellbookError when lookups are disabled, the deck holds
        no cards, or the service fails and nothing is cached. When the
        service is unreachable or rate-limiting, an expired cached report
        for the same cards is returned instead, its note saying how old.
        """
        if os.environ.get(OPT_OUT_ENV):
            raise SpellbookError(f"Combo lookups disabled ({OPT_OUT_ENV})")
        query = deck_query(deck)
        if not query.main and not query.commanders:
            raise SpellbookError("No cards in the deck to look up")
        fixture = os.environ.get(FIXTURE_ENV)
        if fixture:
            return _from_fixture(Path(fixture), query)
        key = query.cache_key()
        cached = self._read_cache(key)
        if cached is not None and cached[1] <= self._max_age_seconds:
            return cached[0]
        try:
            data = _fetch_remote(query)
        except _UnreachableError as exc:
            if cached is None:
                raise
            days = int(cached[1] // 86400)
            return replace(cached[0], note=f"cached {days} days ago ({exc.reason})")
        report = parse_report(data, query.names)
        self._write_cache(key, report)
        return report

    def _cache_path(self, key: str) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / "spellbook" / f"{key}.json"

    def _read_cache(self, key: str) -> tuple[ComboReport, float] | None:
        """The cached report and its age in seconds, however old."""
        path = self._cache_path(key)
        if path is None:
            return None
        try:
            age = time.time() - path.stat().st_mtime
            report = _report_from_json(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, KeyError):
            return None
        return report, age

    def _write_cache(self, key: str, report: ComboReport) -> None:
        path = self._cache_path(key)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            doc = {"version": _CACHE_VERSION, **asdict(replace(report, note=""))}
            path.write_text(json.dumps(doc), encoding="utf-8")
        except OSError:
            pass  # cache is best-effort; the lookup already succeeded


def _report_from_json(doc: Any) -> ComboReport:
    """A report _write_cache wrote; raises on anything else."""
    if not isinstance(doc, dict) or doc.get("version") != _CACHE_VERSION:
        raise ValueError("not a cached combo report")

    def combo(c: Any) -> Combo:
        return Combo(
            id=str(c["id"]),
            cards=tuple(c["cards"]),
            produces=tuple(c["produces"]),
            identity=str(c["identity"]),
            description=str(c["description"]),
            mana_needed=str(c["mana_needed"]),
            popularity=int(c["popularity"]),
            missing=tuple(c["missing"]),
        )

    return ComboReport(
        included=tuple(map(combo, doc["included"])),
        one_away=tuple(map(combo, doc["one_away"])),
    )


def _from_fixture(path: Path, query: DeckQuery) -> ComboReport:
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SpellbookError(f"{FIXTURE_ENV}: cannot read {path}: {exc}") from exc
    report = parse_report(data, query.names)
    return replace(report, note=f"recorded response from {path.name} ({FIXTURE_ENV})")


def _fetch_remote(query: DeckQuery) -> object:
    try:
        response = httpx.post(
            FIND_MY_COMBOS_URL,
            json=query.payload(),
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code == 429 or response.status_code >= 500:
            response.raise_for_status()
    except httpx.HTTPError as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 0
        reason = (
            f"{SERVICE} is rate-limiting" if status == 429
            else f"{SERVICE} is unavailable" if status
            else "offline"
        )
        message = describe_network_error(
            exc, service=SERVICE, host="backend.commanderspellbook.com", retry="try again"
        )
        raise _UnreachableError(message, reason) from exc
    if response.status_code != 200:
        raise SpellbookError(
            f"{SERVICE} rejected the lookup (HTTP {response.status_code})"
            + _rejection_detail(response)
        )
    try:
        return response.json()
    except ValueError as exc:
        raise SpellbookError(f"{SERVICE} returned invalid JSON") from exc


def _rejection_detail(response: httpx.Response) -> str:
    """': <first message>' from a 4xx validation body, else ''."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        for value in body.values():
            first = value[0] if isinstance(value, list) and value else value
            if isinstance(first, str) and first:
                return f": {first}"
    return ""

"""Scryfall bulk data download and import.

Scryfall's bulk-data manifest historically exposed a plain-JSON array
via ``download_uri``; the feed now serves gzipped JSONL (one card per
line) via ``jsonl_download_uri``. Both shapes are supported: the
manifest decides what gets downloaded, and the cache file's extension
decides how it is parsed.
"""

import gzip
import json
import os
import sqlite3
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from vimtg import __version__
from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card

BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
USER_AGENT = f"vimtg/{__version__}"
# Scryfall's API guidelines ask every client to send both headers
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json;q=0.9,*/*;q=0.8",
}
# 429 / 503 handling: honor Retry-After, but never stall a sync for long
MAX_ATTEMPTS = 3
DEFAULT_RETRY_AFTER = 2.0
MAX_RETRY_AFTER = 60.0
_RETRY_STATUSES = frozenset({429, 503})
MAX_AGE_DAYS = 7
CHUNK_SIZE = 65536
SKIP_LAYOUTS = frozenset({"token", "double_faced_token", "emblem", "art_series"})
PROGRESS_INTERVAL = 5000

# Known cache file names, newest format first. Old installs may still
# hold a fresh oracle_cards.json — it stays parseable.
CACHE_FILENAMES = ("oracle_cards.jsonl.gz", "oracle_cards.jsonl", "oracle_cards.json")

ProgressFn = Callable[[int, int], None]
SyncProgressFn = Callable[[str, int, int], None]

_sleep = time.sleep  # patched by tests


def _retry_delay(resp: httpx.Response) -> float:
    """Seconds to wait before retrying, from Retry-After when it is usable."""
    raw = resp.headers.get("retry-after", "")
    try:
        delay = float(raw)
    except ValueError:
        delay = DEFAULT_RETRY_AFTER  # absent, or an HTTP-date
    return min(max(delay, 0.0), MAX_RETRY_AFTER)


_PROXY_ENV = ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")


def _proxy_hint() -> str:
    """' (via proxy <url>)' when a proxy is configured, else ''."""
    for var in _PROXY_ENV:
        raw = os.environ.get(var)
        if raw:
            # host[:port] only — the URL may carry credentials
            parsed = urlsplit(raw if "//" in raw else f"//{raw}")
            host = parsed.hostname or "?"
            port = f":{parsed.port}" if parsed.port else ""
            return f" (via proxy {host}{port})"
    return ""


def describe_sync_error(
    exc: BaseException, retry: str = "run `vimtg sync` to retry"
) -> str:
    """A user-facing explanation of a failed sync, with how to retry.

    `retry` is the retry advice for where the message shows (the CLI
    says `vimtg sync`, the editor says :sync).
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return f"Scryfall is rate-limiting requests — wait a minute, then {retry}"
        if status == 407:
            return (
                f"The proxy{_proxy_hint()} wants authentication — put the "
                f"credentials in HTTPS_PROXY, then {retry}"
            )
        if status >= 500:
            return f"Scryfall is unavailable (HTTP {status}) — {retry} later"
        return f"Scryfall returned HTTP {status} — {retry}"
    if isinstance(exc, httpx.ProxyError):
        return (
            f"The proxy{_proxy_hint()} refused the connection ({exc}) — "
            f"check HTTPS_PROXY, then {retry}"
        )
    if isinstance(exc, httpx.TimeoutException):
        return f"Timed out talking to Scryfall — check your connection and {retry}"
    if isinstance(exc, httpx.ConnectError):
        text = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in text or "certificate" in text.lower():
            return (
                "Could not verify Scryfall's TLS certificate — a proxy or "
                "firewall may be intercepting HTTPS (point SSL_CERT_FILE at "
                f"its CA bundle), then {retry}"
            )
        return (
            f"Could not reach api.scryfall.com{_proxy_hint()} — you seem to "
            f"be offline; {retry} once connected"
        )
    if isinstance(exc, httpx.HTTPError):
        return f"Could not reach Scryfall ({exc}) — check your connection and {retry}"
    if isinstance(exc, sqlite3.Error):
        return f"Card database error ({exc}) — {retry}"
    return f"{exc} — {retry}"


def _parse_sync_time(last_sync: str | None) -> datetime | None:
    if not last_sync:
        return None
    try:
        when = datetime.fromisoformat(last_sync)
    except ValueError:
        return None
    return when if when.tzinfo is not None else when.replace(tzinfo=UTC)


def card_data_date(last_sync: str | None) -> str | None:
    """The sync date as YYYY-MM-DD, or None when unknown."""
    when = _parse_sync_time(last_sync)
    return when.date().isoformat() if when is not None else None


def card_data_age_days(
    last_sync: str | None, now: datetime | None = None
) -> int | None:
    """Whole days since the last sync, or None when unknown."""
    when = _parse_sync_time(last_sync)
    if when is None:
        return None
    now = now or datetime.now(UTC)
    return max(0, (now - when).days)


NO_CARD_DATA = "no card data - :sync to download"


def card_data_badge(
    count: int, last_sync: str | None, now: datetime | None = None,
) -> tuple[str, bool]:
    """(status-line text, needs attention) for the card database.

    Attention means there is nothing to search, or the data is older
    than MAX_AGE_DAYS.
    """
    if count <= 0:
        return NO_CARD_DATA, True
    date = card_data_date(last_sync)
    if date is None:
        return "card data date unknown - :sync to refresh", True
    age = card_data_age_days(last_sync, now) or 0
    return f"card data as of {date}", age > MAX_AGE_DAYS


def card_data_note(
    count: int, last_sync: str | None, now: datetime | None = None,
) -> str | None:
    """An informational line for CLI output when card data is stale."""
    if count <= 0:
        return None
    age = card_data_age_days(last_sync, now)
    date = card_data_date(last_sync)
    if age is None or date is None or age <= MAX_AGE_DAYS:
        return None
    return (
        f"note: card data as of {date} ({age} days old) — "
        "run `vimtg sync` to refresh legality and new cards"
    )


def sync_is_due(
    repo: CardRepository, max_age_days: int = MAX_AGE_DAYS
) -> bool:
    """True when the card database is empty or its last sync is stale."""
    if repo.count() == 0:
        return True
    last = repo.get_last_sync()
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=UTC)
    age = datetime.now(UTC) - last_dt
    return age.total_seconds() > max_age_days * 86400


class ScryfallSync:
    def __init__(self, card_repo: CardRepository, cache_dir: Path) -> None:
        self._repo = card_repo
        self._cache_dir = cache_dir
        self.last_skipped = 0  # cards that failed to parse in the last load

    def get_bulk_data_url(self) -> str:
        """Fetch bulk-data manifest, return URL for oracle_cards.

        Prefers the legacy plain-JSON ``download_uri`` when present and
        falls back to ``jsonl_download_uri`` (the current feed shape).
        """
        for attempt in range(1, MAX_ATTEMPTS + 1):
            resp = httpx.get(BULK_DATA_URL, headers=HEADERS, timeout=30)
            if resp.status_code not in _RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                break
            _sleep(_retry_delay(resp))
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("data", []):
            if item.get("type") == "oracle_cards":
                uri = item.get("download_uri") or item.get("jsonl_download_uri")
                if uri:
                    return str(uri)
                raise RuntimeError(
                    "oracle_cards entry has no download URL — Scryfall "
                    "manifest format may have changed"
                )
        raise RuntimeError("oracle_cards bulk data not found")

    def download(
        self,
        url: str,
        dest: Path,
        progress: ProgressFn | None = None,
    ) -> Path:
        """Stream download to temp file, verify size, atomic rename.

        A truncated download must not be renamed into place — the cache
        freshness check would then serve broken JSON for a week.
        """
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                if self._download_once(url, tmp, progress, attempt == MAX_ATTEMPTS):
                    break
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        # os.replace, not rename: rename refuses an existing dest on Windows
        os.replace(tmp, dest)
        return dest

    def _download_once(
        self, url: str, tmp: Path, progress: ProgressFn | None, last: bool,
    ) -> bool:
        """One download attempt; False when rate-limited and worth retrying.

        Truncation is judged on raw bytes off the wire: Content-Length
        counts the encoded body, so comparing the decoded length would
        reject every good response sent with a Content-Encoding.
        """
        with httpx.stream(
            "GET", url, headers=HEADERS, timeout=300, follow_redirects=True,
        ) as resp:
            if resp.status_code in _RETRY_STATUSES and not last:
                _sleep(_retry_delay(resp))
                return False
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            written = 0
            with open(tmp, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=CHUNK_SIZE):
                    f.write(chunk)
                    written += len(chunk)
                    if progress:
                        progress(resp.num_bytes_downloaded or written, total)
            # num_bytes_downloaded counts raw bytes; it stays 0 only for a
            # body that was never streamed, where raw and decoded agree
            received = resp.num_bytes_downloaded or written
        if total and received != total:
            raise RuntimeError(
                f"Truncated download: got {received} of {total} bytes"
            )
        return True

    def parse_and_load(
        self,
        json_path: Path,
        progress: ProgressFn | None = None,
    ) -> int:
        """Parse a bulk file (JSON array or [gzipped] JSONL), load cards.

        Raises RuntimeError when no card parses at all — that means the
        feed shape changed, not that the sync "succeeded with 0 cards".
        Tracks skip count so partial failures are visible to callers.
        """
        name = json_path.name
        try:
            if name.endswith((".jsonl.gz", ".jsonl")):
                items = list(_iter_jsonl(json_path))
            else:
                with open(json_path, encoding="utf-8") as f:
                    items = json.load(f)
        except (json.JSONDecodeError, gzip.BadGzipFile, EOFError, UnicodeDecodeError) as exc:
            # Corrupt cache: remove it so the next sync re-downloads
            json_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Corrupt card cache (deleted, retry sync): {exc}"
            ) from exc

        return self._load_items(items, progress)

    def _load_items(
        self,
        items: Iterable[dict[str, Any]],
        progress: ProgressFn | None = None,
    ) -> int:
        cards: list[Card] = []
        self.last_skipped = 0
        items = list(items)
        total = len(items)
        for i, item in enumerate(items):
            if item.get("layout") in SKIP_LAYOUTS:
                continue
            try:
                cards.append(Card.from_scryfall(item))
            except Exception:  # noqa: BLE001
                self.last_skipped += 1
                continue
            if progress and i % PROGRESS_INTERVAL == 0:
                progress(i, total)

        if total > 0 and not cards:
            raise RuntimeError(
                f"No cards parsed from {total} entries — Scryfall feed "
                "format may have changed"
            )

        # Reload, don't merge: a re-keyed representative printing or a
        # card Scryfall dropped must not survive as a stale row.
        count = self._repo.replace_all(cards, synced_at=datetime.now(UTC).isoformat())
        if progress:
            progress(total, total)
        return count

    def _fresh_cache(self, force: bool) -> Path | None:
        """The freshest usable cache file, or None when a download is due."""
        if force:
            return None
        candidates = [
            p
            for p in (self._cache_dir / n for n in CACHE_FILENAMES)
            if p.exists()
        ]
        if not candidates:
            return None
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
        age_days = (time.time() - newest.stat().st_mtime) / 86400
        return newest if age_days < MAX_AGE_DAYS else None

    def _dest_for_url(self, url: str) -> Path:
        """Cache path matching the manifest URL's format."""
        base = url.split("?", 1)[0]
        if base.endswith(".jsonl.gz"):
            return self._cache_dir / "oracle_cards.jsonl.gz"
        if base.endswith(".jsonl"):
            return self._cache_dir / "oracle_cards.jsonl"
        return self._cache_dir / "oracle_cards.json"

    def sync(
        self,
        force: bool = False,
        progress: SyncProgressFn | None = None,
    ) -> int:
        """Full sync: download oracle_cards if needed, parse, load."""
        cached = self._fresh_cache(force)
        if cached is not None:
            if progress:
                progress("parse", 0, 0)
            # The load records the sync time, so sync_is_due() sees a
            # populated, fresh DB
            return self.parse_and_load(cached, _wrap_progress(progress, "parse"))

        if progress:
            progress("download", 0, 0)
        url = self.get_bulk_data_url()
        dest = self._dest_for_url(url)
        self.download(url, dest, _wrap_progress(progress, "download"))

        if progress:
            progress("parse", 0, 0)
        return self.parse_and_load(dest, _wrap_progress(progress, "parse"))


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield objects from a JSONL file, transparently gunzipping .gz."""
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _wrap_progress(
    progress: SyncProgressFn | None,
    phase: str,
) -> ProgressFn | None:
    """Wrap a (str, int, int) callback into a (int, int) callback."""
    if progress is None:
        return None
    return lambda current, total: progress(phase, current, total)

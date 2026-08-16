"""Scryfall bulk data download and import.

Scryfall's bulk-data manifest historically exposed a plain-JSON array
via ``download_uri``; the feed now serves gzipped JSONL (one card per
line) via ``jsonl_download_uri``. Both shapes are supported: the
manifest decides what gets downloaded, and the cache file's extension
decides how it is parsed.
"""

import gzip
import json
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card

BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
USER_AGENT = "vimtg/0.1.0"
MAX_AGE_DAYS = 7
CHUNK_SIZE = 65536
SKIP_LAYOUTS = frozenset({"token", "double_faced_token", "emblem", "art_series"})
PROGRESS_INTERVAL = 5000

# Known cache file names, newest format first. Old installs may still
# hold a fresh oracle_cards.json — it stays parseable.
CACHE_FILENAMES = ("oracle_cards.jsonl.gz", "oracle_cards.jsonl", "oracle_cards.json")

ProgressFn = Callable[[int, int], None]
SyncProgressFn = Callable[[str, int, int], None]


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
        resp = httpx.get(
            BULK_DATA_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
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
            with httpx.stream(
                "GET",
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=300,
                follow_redirects=True,
            ) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=CHUNK_SIZE):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            progress(downloaded, total)
            if total and downloaded != total:
                raise RuntimeError(
                    f"Truncated download: got {downloaded} of {total} bytes"
                )
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        tmp.rename(dest)
        return dest

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

        count = self._repo.bulk_insert(cards)
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
            count = self.parse_and_load(
                cached, _wrap_progress(progress, "parse")
            )
            # Record the load so sync_is_due() sees a populated, fresh DB
            self._repo.set_last_sync(datetime.now(UTC).isoformat())
            return count

        if progress:
            progress("download", 0, 0)
        url = self.get_bulk_data_url()
        dest = self._dest_for_url(url)
        self.download(url, dest, _wrap_progress(progress, "download"))

        if progress:
            progress("parse", 0, 0)
        count = self.parse_and_load(dest, _wrap_progress(progress, "parse"))

        self._repo.set_last_sync(datetime.now(UTC).isoformat())
        return count


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

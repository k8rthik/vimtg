"""Scryfall bulk data download and import."""

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card

BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
USER_AGENT = "vimtg/0.1.0"
MAX_AGE_DAYS = 7
CHUNK_SIZE = 65536
SKIP_LAYOUTS = frozenset({"token", "double_faced_token", "emblem", "art_series"})
PROGRESS_INTERVAL = 5000

ProgressFn = Callable[[int, int], None]
SyncProgressFn = Callable[[str, int, int], None]


class ScryfallSync:
    def __init__(self, card_repo: CardRepository, cache_dir: Path) -> None:
        self._repo = card_repo
        self._cache_dir = cache_dir

    def get_bulk_data_url(self) -> str:
        """Fetch bulk-data manifest, return URL for oracle_cards."""
        resp = httpx.get(
            BULK_DATA_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("data", []):
            if item.get("type") == "oracle_cards":
                return item["download_uri"]
        raise RuntimeError("oracle_cards bulk data not found")

    def download(
        self,
        url: str,
        dest: Path,
        progress: ProgressFn | None = None,
    ) -> Path:
        """Stream download to temp file, atomic rename."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
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
        tmp.rename(dest)
        return dest

    def parse_and_load(
        self,
        json_path: Path,
        progress: ProgressFn | None = None,
    ) -> int:
        """Parse bulk JSON, load cards into repository."""
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        cards: list[Card] = []
        total = len(data)
        for i, item in enumerate(data):
            if item.get("layout") in SKIP_LAYOUTS:
                continue
            try:
                cards.append(Card.from_scryfall(item))
            except Exception:  # noqa: BLE001
                continue
            if progress and i % PROGRESS_INTERVAL == 0:
                progress(i, total)

        count = self._repo.bulk_insert(cards)
        if progress:
            progress(total, total)
        return count

    def sync(
        self,
        force: bool = False,
        progress: SyncProgressFn | None = None,
    ) -> int:
        """Full sync: download oracle_cards if needed, parse, load."""
        json_path = self._cache_dir / "oracle_cards.json"

        if not force and json_path.exists():
            age_days = (time.time() - json_path.stat().st_mtime) / 86400
            if age_days < MAX_AGE_DAYS:
                if progress:
                    progress("parse", 0, 0)
                return self.parse_and_load(
                    json_path,
                    _wrap_progress(progress, "parse"),
                )

        if progress:
            progress("download", 0, 0)
        url = self.get_bulk_data_url()
        self.download(url, json_path, _wrap_progress(progress, "download"))

        if progress:
            progress("parse", 0, 0)
        count = self.parse_and_load(json_path, _wrap_progress(progress, "parse"))

        self._repo.set_last_sync(datetime.now(UTC).isoformat())
        return count


def _wrap_progress(
    progress: SyncProgressFn | None,
    phase: str,
) -> ProgressFn | None:
    """Wrap a (str, int, int) callback into a (int, int) callback."""
    if progress is None:
        return None
    return lambda current, total: progress(phase, current, total)

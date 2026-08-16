"""Tests for ScryfallSync bulk data download and import."""

import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.scryfall_sync import ScryfallSync

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def card_repo(db_factory: Callable[..., Database]) -> CardRepository:
    return CardRepository(db_factory())


@pytest.fixture
def syncer(card_repo: CardRepository, tmp_path: Path) -> ScryfallSync:
    return ScryfallSync(card_repo=card_repo, cache_dir=tmp_path / "cache")


@pytest.fixture
def sample_json_path(tmp_path: Path) -> Path:
    """Copy fixture JSON to a temp location for parse tests."""
    src = FIXTURES_DIR / "scryfall_sample.json"
    dest = tmp_path / "oracle_cards.json"
    dest.write_text(src.read_text())
    return dest


class TestParseAndLoad:
    def test_loads_fixture_cards(self, syncer: ScryfallSync, sample_json_path: Path) -> None:
        count = syncer.parse_and_load(sample_json_path)
        assert count == 10

    def test_skips_tokens(self, syncer: ScryfallSync, tmp_path: Path) -> None:
        """Token layout cards should be skipped."""
        data = [
            {
                "id": "token-001",
                "name": "Soldier Token",
                "mana_cost": "",
                "cmc": 0.0,
                "type_line": "Token Creature — Soldier",
                "oracle_text": "",
                "colors": ["W"],
                "color_identity": ["W"],
                "power": "1",
                "toughness": "1",
                "keywords": [],
                "set": "m21",
                "rarity": "common",
                "layout": "token",
                "legalities": {},
                "prices": {"usd": None},
                "image_uris": {"normal": "https://example.com/token.jpg"},
            },
            {
                "id": "real-001",
                "name": "Plains",
                "mana_cost": "",
                "cmc": 0.0,
                "type_line": "Basic Land — Plains",
                "oracle_text": "({T}: Add {W}.)",
                "colors": [],
                "color_identity": ["W"],
                "power": None,
                "toughness": None,
                "keywords": [],
                "set": "m21",
                "rarity": "common",
                "layout": "normal",
                "legalities": {"standard": "legal"},
                "prices": {"usd": None},
                "image_uris": {"normal": "https://example.com/plains.jpg"},
            },
        ]
        json_path = tmp_path / "test_tokens.json"
        json_path.write_text(json.dumps(data))
        count = syncer.parse_and_load(json_path)
        assert count == 1

    def test_all_fixtures_parse(self, syncer: ScryfallSync, sample_json_path: Path) -> None:
        """All 10 sample cards should parse successfully."""
        count = syncer.parse_and_load(sample_json_path)
        assert count == 10
        assert syncer._repo.count() == 10

    def test_progress_callback(self, syncer: ScryfallSync, sample_json_path: Path) -> None:
        calls: list[tuple[int, int]] = []
        syncer.parse_and_load(sample_json_path, progress=lambda c, t: calls.append((c, t)))
        assert len(calls) > 0
        last_call = calls[-1]
        assert last_call[0] == last_call[1]  # final call: current == total

    def test_skips_unparseable(self, syncer: ScryfallSync, tmp_path: Path) -> None:
        """Cards that fail to parse should be skipped."""
        data = [
            {"layout": "normal"},  # missing required "id" field
            {
                "id": "good-001",
                "name": "Valid Card",
                "mana_cost": "{W}",
                "cmc": 1.0,
                "type_line": "Creature",
                "oracle_text": "Test",
                "colors": ["W"],
                "color_identity": ["W"],
                "power": "1",
                "toughness": "1",
                "keywords": [],
                "set": "tst",
                "rarity": "common",
                "layout": "normal",
                "legalities": {},
                "prices": {"usd": None},
                "image_uris": {"normal": "https://example.com/card.jpg"},
            },
        ]
        json_path = tmp_path / "test_bad.json"
        json_path.write_text(json.dumps(data))
        count = syncer.parse_and_load(json_path)
        assert count == 1


class TestGetBulkDataUrl:
    def test_extracts_oracle_cards_url(self, syncer: ScryfallSync) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"type": "default_cards", "download_uri": "https://example.com/default.json"},
                {"type": "oracle_cards", "download_uri": "https://example.com/oracle.json"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("vimtg.data.scryfall_sync.httpx.get", return_value=mock_response):
            url = syncer.get_bulk_data_url()
        assert url == "https://example.com/oracle.json"

    def test_raises_when_not_found(self, syncer: ScryfallSync) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"type": "default_cards", "download_uri": "https://example.com/default.json"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch("vimtg.data.scryfall_sync.httpx.get", return_value=mock_response),
            pytest.raises(RuntimeError, match="oracle_cards"),
        ):
            syncer.get_bulk_data_url()


def _mock_stream(chunks: list[bytes], content_length: int | None = None):
    """Build a MagicMock standing in for httpx.stream(...) as a context manager."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    total = content_length if content_length is not None else sum(len(c) for c in chunks)
    resp.headers = {"content-length": str(total)}
    resp.iter_bytes = MagicMock(return_value=iter(chunks))
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


class TestDownload:
    def test_streams_to_file_with_atomic_rename(
        self, syncer: ScryfallSync, tmp_path: Path
    ) -> None:
        dest = tmp_path / "out.json"
        chunks = [b'[{"id":', b'"x"}]']
        with patch(
            "vimtg.data.scryfall_sync.httpx.stream",
            return_value=_mock_stream(chunks),
        ):
            result = syncer.download("https://example.com/x.json", dest)
        assert result == dest
        assert dest.exists()
        assert dest.read_bytes() == b'[{"id":"x"}]'
        # The temp file should have been renamed away.
        assert not dest.with_suffix(".tmp").exists()

    def test_progress_callback_invoked(
        self, syncer: ScryfallSync, tmp_path: Path
    ) -> None:
        dest = tmp_path / "out.json"
        calls: list[tuple[int, int]] = []
        with patch(
            "vimtg.data.scryfall_sync.httpx.stream",
            return_value=_mock_stream([b"ab", b"cd"], content_length=4),
        ):
            syncer.download(
                "https://example.com/x.json", dest, progress=lambda c, t: calls.append((c, t))
            )
        assert calls == [(2, 4), (4, 4)]


class TestSync:
    def test_sync_uses_cache(
        self, card_repo: CardRepository, tmp_path: Path, sample_json_path: Path
    ) -> None:
        """If oracle_cards.json exists and is fresh, skip download."""
        cache = tmp_path / "sync_cache"
        cache.mkdir()
        cached_json = cache / "oracle_cards.json"
        cached_json.write_text((FIXTURES_DIR / "scryfall_sample.json").read_text())

        syncer = ScryfallSync(card_repo=card_repo, cache_dir=cache)
        count = syncer.sync(force=False)
        assert count == 10

    def test_sync_force_downloads(
        self, card_repo: CardRepository, tmp_path: Path
    ) -> None:
        """force=True downloads even when a fresh cache exists."""
        cache = tmp_path / "sync_cache"
        cache.mkdir()
        sample = (FIXTURES_DIR / "scryfall_sample.json").read_text()
        # Stale-looking pre-existing cache; force should ignore it.
        (cache / "oracle_cards.json").write_text("[]")

        syncer = ScryfallSync(card_repo=card_repo, cache_dir=cache)

        def fake_download(url: str, dest: Path, progress=None) -> Path:
            dest.write_text(sample)
            return dest

        phases: list[str] = []
        with (
            patch.object(syncer, "get_bulk_data_url", return_value="https://x/oracle.json"),
            patch.object(syncer, "download", side_effect=fake_download),
        ):
            count = syncer.sync(force=True, progress=lambda p, c, t: phases.append(p))
        assert count == 10
        assert card_repo.get_last_sync() is not None
        assert "download" in phases
        assert "parse" in phases

    def test_sync_stale_cache_redownloads(
        self, card_repo: CardRepository, tmp_path: Path
    ) -> None:
        """A cache older than MAX_AGE_DAYS triggers a fresh download."""
        import os
        import time as _time

        from vimtg.data.scryfall_sync import MAX_AGE_DAYS

        cache = tmp_path / "sync_cache"
        cache.mkdir()
        sample = (FIXTURES_DIR / "scryfall_sample.json").read_text()
        stale = cache / "oracle_cards.json"
        stale.write_text("[]")
        old = _time.time() - (MAX_AGE_DAYS + 1) * 86400
        os.utime(stale, (old, old))

        syncer = ScryfallSync(card_repo=card_repo, cache_dir=cache)
        downloaded: list[str] = []

        def fake_download(url: str, dest: Path, progress=None) -> Path:
            downloaded.append(url)
            dest.write_text(sample)
            return dest

        with (
            patch.object(syncer, "get_bulk_data_url", return_value="https://x/oracle.json"),
            patch.object(syncer, "download", side_effect=fake_download),
        ):
            count = syncer.sync(force=False)
        assert downloaded == ["https://x/oracle.json"]
        assert count == 10

    def test_sync_progress_phases_reported(
        self, card_repo: CardRepository, tmp_path: Path
    ) -> None:
        cache = tmp_path / "sync_cache"
        cache.mkdir()
        (cache / "oracle_cards.json").write_text(
            (FIXTURES_DIR / "scryfall_sample.json").read_text()
        )
        syncer = ScryfallSync(card_repo=card_repo, cache_dir=cache)
        phases: list[str] = []
        syncer.sync(force=False, progress=lambda phase, c, t: phases.append(phase))
        assert "parse" in phases


def _minimal_card(card_id: str, name: str) -> dict:
    """Smallest Scryfall dict that Card.from_scryfall accepts."""
    return {
        "id": card_id,
        "name": name,
        "mana_cost": "{R}",
        "cmc": 1.0,
        "type_line": "Instant",
        "oracle_text": "",
        "colors": ["R"],
        "color_identity": ["R"],
        "power": None,
        "toughness": None,
        "keywords": [],
        "set": "tst",
        "rarity": "common",
        "layout": "normal",
        "legalities": {},
        "prices": {"usd": None},
        "image_uris": {"normal": "https://example.com/c.jpg"},
    }


class TestJsonlManifest:
    """Scryfall replaced download_uri with jsonl_download_uri (gzipped JSONL)."""

    def _url_for_manifest(self, syncer: ScryfallSync, item: dict) -> str:
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [item]}
        mock_response.raise_for_status = MagicMock()
        with patch("vimtg.data.scryfall_sync.httpx.get", return_value=mock_response):
            return syncer.get_bulk_data_url()

    def test_jsonl_uri_fallback(self, syncer: ScryfallSync) -> None:
        url = self._url_for_manifest(syncer, {
            "type": "oracle_cards",
            "jsonl_download_uri": "https://example.com/oracle.jsonl.gz",
        })
        assert url == "https://example.com/oracle.jsonl.gz"

    def test_legacy_uri_preferred_when_both(self, syncer: ScryfallSync) -> None:
        url = self._url_for_manifest(syncer, {
            "type": "oracle_cards",
            "download_uri": "https://example.com/oracle.json",
            "jsonl_download_uri": "https://example.com/oracle.jsonl.gz",
        })
        assert url == "https://example.com/oracle.json"

    def test_no_url_at_all_raises(self, syncer: ScryfallSync) -> None:
        with pytest.raises(RuntimeError, match="no download URL"):
            self._url_for_manifest(syncer, {"type": "oracle_cards"})

    def test_dest_matches_url_format(self, syncer: ScryfallSync) -> None:
        assert syncer._dest_for_url(
            "https://x/o.jsonl.gz"
        ).name == "oracle_cards.jsonl.gz"
        assert syncer._dest_for_url("https://x/o.jsonl").name == "oracle_cards.jsonl"
        assert syncer._dest_for_url("https://x/o.json").name == "oracle_cards.json"


class TestJsonlParse:
    def test_parses_gzipped_jsonl(self, syncer: ScryfallSync, tmp_path: Path) -> None:
        import gzip

        lines = [
            json.dumps(_minimal_card("a-1", "Shock")),
            json.dumps(_minimal_card("a-2", "Lightning Bolt")),
        ]
        path = tmp_path / "oracle_cards.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        assert syncer.parse_and_load(path) == 2

    def test_parses_plain_jsonl(self, syncer: ScryfallSync, tmp_path: Path) -> None:
        path = tmp_path / "oracle_cards.jsonl"
        path.write_text(json.dumps(_minimal_card("a-1", "Shock")) + "\n")
        assert syncer.parse_and_load(path) == 1

    def test_corrupt_gzip_deleted_and_raises(
        self, syncer: ScryfallSync, tmp_path: Path
    ) -> None:
        path = tmp_path / "oracle_cards.jsonl.gz"
        path.write_bytes(b"not gzip at all")
        with pytest.raises(RuntimeError, match="Corrupt card cache"):
            syncer.parse_and_load(path)
        assert not path.exists()

    def test_sync_uses_fresh_jsonl_cache(
        self, card_repo: CardRepository, tmp_path: Path
    ) -> None:
        import gzip

        cache = tmp_path / "sync_cache"
        cache.mkdir()
        with gzip.open(cache / "oracle_cards.jsonl.gz", "wt", encoding="utf-8") as f:
            f.write(json.dumps(_minimal_card("a-1", "Shock")) + "\n")
        syncer = ScryfallSync(card_repo=card_repo, cache_dir=cache)
        assert syncer.sync(force=False) == 1
        # Cached loads also stamp last_sync so sync_is_due() settles
        assert card_repo.get_last_sync() is not None

    def test_fresh_cache_prefers_newest_file(
        self, card_repo: CardRepository, tmp_path: Path
    ) -> None:
        import gzip
        import os as _os
        import time as _time

        cache = tmp_path / "sync_cache"
        cache.mkdir()
        old_json = cache / "oracle_cards.json"
        old_json.write_text(json.dumps([_minimal_card("a-1", "Old Card")]))
        older = _time.time() - 3600
        _os.utime(old_json, (older, older))
        with gzip.open(cache / "oracle_cards.jsonl.gz", "wt", encoding="utf-8") as f:
            f.write(json.dumps(_minimal_card("a-2", "New Card")) + "\n")

        syncer = ScryfallSync(card_repo=card_repo, cache_dir=cache)
        syncer.sync(force=False)
        assert card_repo.get_by_name("New Card") is not None
        assert card_repo.get_by_name("Old Card") is None


class TestSyncIsDue:
    def test_empty_repo_is_due(self, card_repo: CardRepository) -> None:
        from vimtg.data.scryfall_sync import sync_is_due

        assert sync_is_due(card_repo)

    def _populate(self, card_repo: CardRepository) -> None:
        from vimtg.domain.card import Card

        card_repo.bulk_insert([Card.from_scryfall(_minimal_card("a-1", "Shock"))])

    def test_populated_without_timestamp_is_due(
        self, card_repo: CardRepository
    ) -> None:
        from vimtg.data.scryfall_sync import sync_is_due

        self._populate(card_repo)
        assert sync_is_due(card_repo)

    def test_recent_sync_not_due(self, card_repo: CardRepository) -> None:
        from datetime import UTC, datetime

        from vimtg.data.scryfall_sync import sync_is_due

        self._populate(card_repo)
        card_repo.set_last_sync(datetime.now(UTC).isoformat())
        assert not sync_is_due(card_repo)

    def test_stale_sync_is_due(self, card_repo: CardRepository) -> None:
        from datetime import UTC, datetime, timedelta

        from vimtg.data.scryfall_sync import MAX_AGE_DAYS, sync_is_due

        self._populate(card_repo)
        old = datetime.now(UTC) - timedelta(days=MAX_AGE_DAYS + 1)
        card_repo.set_last_sync(old.isoformat())
        assert sync_is_due(card_repo)

    def test_garbage_timestamp_is_due(self, card_repo: CardRepository) -> None:
        from vimtg.data.scryfall_sync import sync_is_due

        self._populate(card_repo)
        card_repo.set_last_sync("not-a-date")
        assert sync_is_due(card_repo)

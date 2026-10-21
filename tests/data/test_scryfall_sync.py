"""Tests for ScryfallSync bulk data download and import."""

import gzip
import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
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
    resp.status_code = 200
    resp.num_bytes_downloaded = 0

    def _iter_bytes(chunk_size: int | None = None):
        for chunk in chunks:
            resp.num_bytes_downloaded += len(chunk)
            yield chunk

    resp.iter_bytes = MagicMock(side_effect=_iter_bytes)
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


class TestResyncReplacesCardTable:
    """Each sync reloads the cards table: a changed representative
    printing (new scryfall_id, same oracle card) must not leave a twin."""

    def test_second_sync_with_new_printing_leaves_one_row(
        self,
        syncer: ScryfallSync,
        card_repo: CardRepository,
        real_shape_cards: list[dict[str, object]],
        tmp_path: Path,
    ) -> None:
        first = tmp_path / "first.json"
        first.write_text(json.dumps(real_shape_cards), encoding="utf-8")
        syncer.parse_and_load(first)

        reprinted = [
            {**d, "id": "reprint-bolt", "set": "2x2", "legalities": {"modern": "banned"}}
            if d["name"] == "Lightning Bolt"
            else d
            for d in real_shape_cards
        ]
        second = tmp_path / "second.json"
        second.write_text(json.dumps(reprinted), encoding="utf-8")
        syncer.parse_and_load(second)

        assert card_repo.count() == len(real_shape_cards)
        assert [c.set_code for c in card_repo.search("Lightning Bolt")] == ["2x2"]
        single = card_repo.get_by_name("Lightning Bolt")
        assert single is not None and single.legalities == {"modern": "banned"}
        assert card_repo.get_by_names(["Lightning Bolt"])["Lightning Bolt"] == single
        assert card_repo.get_last_sync() is not None


# --- HTTP layer: real httpx responses through a MockTransport ---


def _transport_stream(handler):  # type: ignore[no-untyped-def]
    """Stand-in for httpx.stream backed by a MockTransport (no network)."""
    from contextlib import contextmanager

    @contextmanager
    def _stream(method, url, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.pop("timeout", None)
        follow = kwargs.pop("follow_redirects", False)
        with (
            httpx.Client(
                transport=httpx.MockTransport(handler), follow_redirects=follow,
            ) as client,
            client.stream(method, url, **kwargs) as resp,
        ):
            yield resp

    return _stream


def _wire(status: int, body: bytes, headers: dict[str, str] | None = None) -> httpx.Response:
    """A response streamed off the "wire" like a real one (not preloaded)."""
    return httpx.Response(status, stream=httpx.ByteStream(body), headers=headers)


def _transport_get(handler):  # type: ignore[no-untyped-def]
    def _get(url, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.pop("timeout", None)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return client.get(url, **kwargs)

    return _get


ORACLE_MANIFEST = {
    "object": "list",
    "has_more": False,
    "data": [
        {
            "object": "bulk_data",
            "type": "oracle_cards",
            "name": "Oracle Cards",
            "content_type": "application/jsonl",
            "content_encoding": "gzip",
            "download_uri": None,
            "jsonl_download_uri": (
                "https://data.scryfall.io/oracle-cards/oracle-cards-20261010.jsonl.gz"
            ),
        }
    ],
}


class TestHttpLayer:
    def test_requests_send_user_agent_and_accept(self, syncer: ScryfallSync) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=ORACLE_MANIFEST)

        with patch("vimtg.data.scryfall_sync.httpx.get", _transport_get(handler)):
            url = syncer.get_bulk_data_url()
        assert url.endswith(".jsonl.gz")
        assert seen[0].headers["user-agent"].startswith("vimtg/")
        assert "application/json" in seen[0].headers["accept"]

    def test_manifest_429_retries_after_retry_after(
        self, syncer: ScryfallSync, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps: list[float] = []
        monkeypatch.setattr("vimtg.data.scryfall_sync._sleep", sleeps.append)
        responses = [
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(200, json=ORACLE_MANIFEST),
        ]

        with patch(
            "vimtg.data.scryfall_sync.httpx.get",
            _transport_get(lambda request: responses.pop(0)),
        ):
            assert syncer.get_bulk_data_url().endswith(".jsonl.gz")
        assert sleeps == [3.0]

    def test_manifest_429_gives_up_after_max_attempts(
        self, syncer: ScryfallSync, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from vimtg.data.scryfall_sync import MAX_ATTEMPTS, describe_sync_error

        sleeps: list[float] = []
        monkeypatch.setattr("vimtg.data.scryfall_sync._sleep", sleeps.append)
        with (
            patch(
                "vimtg.data.scryfall_sync.httpx.get",
                _transport_get(lambda request: httpx.Response(429)),
            ),
            pytest.raises(httpx.HTTPStatusError) as info,
        ):
            syncer.get_bulk_data_url()
        assert len(sleeps) == MAX_ATTEMPTS - 1
        assert "rate-limiting" in describe_sync_error(info.value)
        assert "vimtg sync" in describe_sync_error(info.value)

    def test_download_429_then_success(
        self, syncer: ScryfallSync, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps: list[float] = []
        monkeypatch.setattr("vimtg.data.scryfall_sync._sleep", sleeps.append)
        responses = [
            httpx.Response(429, headers={"Retry-After": "999"}),
            _wire(200, b"body", {"Content-Length": "4"}),
        ]
        dest = tmp_path / "oracle_cards.json"
        with patch(
            "vimtg.data.scryfall_sync.httpx.stream",
            _transport_stream(lambda request: responses.pop(0)),
        ):
            syncer.download("https://data.scryfall.io/x.json", dest)
        assert dest.read_bytes() == b"body"
        assert sleeps == [60.0]  # Retry-After is capped

    def test_content_encoded_download_not_called_truncated(
        self, syncer: ScryfallSync, tmp_path: Path
    ) -> None:
        """Content-Length counts the encoded body; decoded is longer."""
        body = b'{"object":"card"}\n' * 500
        wire = gzip.compress(body)

        def handler(request: httpx.Request) -> httpx.Response:
            return _wire(
                200, wire, {"Content-Encoding": "gzip", "Content-Length": str(len(wire))},
            )

        dest = tmp_path / "oracle_cards.jsonl"
        with patch("vimtg.data.scryfall_sync.httpx.stream", _transport_stream(handler)):
            syncer.download("https://data.scryfall.io/x.jsonl", dest)
        assert dest.read_bytes() == body

    def test_truncated_download_still_rejected(
        self, syncer: ScryfallSync, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _wire(200, b"short", {"Content-Length": "100"})

        dest = tmp_path / "oracle_cards.json"
        with (
            patch("vimtg.data.scryfall_sync.httpx.stream", _transport_stream(handler)),
            pytest.raises((RuntimeError, httpx.HTTPError)),
        ):
            syncer.download("https://data.scryfall.io/x.json", dest)
        assert not dest.exists()
        assert list(tmp_path.glob("*.tmp")) == []

    def test_download_replaces_existing_cache_file(
        self, syncer: ScryfallSync, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`sync --force` with a cache present: rename onto an existing file
        fails on Windows, so the download must use os.replace."""

        def windows_rename(self: Path, target: object) -> None:
            raise FileExistsError(183, "Cannot create a file when that file already exists")

        monkeypatch.setattr(Path, "rename", windows_rename)
        dest = tmp_path / "oracle_cards.json"
        dest.write_bytes(b"old cache")
        with patch(
            "vimtg.data.scryfall_sync.httpx.stream",
            _transport_stream(lambda request: _wire(200, b"new", {"Content-Length": "3"})),
        ):
            syncer.download("https://data.scryfall.io/x.json", dest)
        assert dest.read_bytes() == b"new"


class TestDescribeSyncError:
    def test_network_error(self) -> None:
        from vimtg.data.scryfall_sync import describe_sync_error

        msg = describe_sync_error(httpx.ConnectError("boom"))
        assert "run `vimtg sync` to retry" in msg

    def test_server_error(self) -> None:
        from vimtg.data.scryfall_sync import describe_sync_error

        request = httpx.Request("GET", "https://api.scryfall.com/bulk-data")
        exc = httpx.HTTPStatusError(
            "x", request=request, response=httpx.Response(503, request=request),
        )
        assert "unavailable" in describe_sync_error(exc)

    def test_runtime_error(self) -> None:
        from vimtg.data.scryfall_sync import describe_sync_error

        assert describe_sync_error(RuntimeError("feed changed")).startswith("feed changed")


class TestUnusableCaches:
    """A feed that holds no cards must never become the card table, and
    must not be kept as a fresh cache for a week."""

    @pytest.mark.parametrize(
        "payload",
        ["[]", '{"object": "error", "details": "x"}', '{"object": "list", "data": []}', "42"],
    )
    def test_empty_or_wrapped_feed_is_an_error_and_the_cache_goes(
        self, syncer: ScryfallSync, tmp_path: Path, payload: str
    ) -> None:
        path = tmp_path / "oracle_cards.json"
        path.write_text(payload, encoding="utf-8")
        with pytest.raises(RuntimeError):
            syncer.parse_and_load(path)
        assert not path.exists()

    def test_non_card_items_are_skipped_not_fatal(
        self, syncer: ScryfallSync, tmp_path: Path
    ) -> None:
        path = tmp_path / "oracle_cards.json"
        path.write_text(
            json.dumps([1, None, "x", {"layout": []}, _minimal_card("c1", "Opt")]),
            encoding="utf-8",
        )
        assert syncer.parse_and_load(path) == 1
        assert syncer.last_skipped == 4

    def test_an_empty_feed_keeps_the_cards_already_synced(
        self, syncer: ScryfallSync, tmp_path: Path
    ) -> None:
        good = tmp_path / "good.json"
        good.write_text(json.dumps([_minimal_card("c1", "Opt")]), encoding="utf-8")
        assert syncer.parse_and_load(good) == 1
        with pytest.raises(RuntimeError):
            syncer._load_items([])
        assert syncer._repo.count() == 1

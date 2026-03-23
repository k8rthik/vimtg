"""Tests for ScryfallSync bulk data download and import."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.scryfall_sync import ScryfallSync

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def card_repo(tmp_db: Path) -> CardRepository:
    db = Database(tmp_db)
    db.initialize()
    return CardRepository(db)


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

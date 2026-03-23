"""Tests for AnalyticsService — compute, caching, invalidation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vimtg.domain.analytics import DeckStats
from vimtg.domain.card import Card
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
from vimtg.services.analytics_service import AnalyticsService


@pytest.fixture
def scryfall_cards() -> list[dict]:
    path = Path(__file__).parent.parent / "fixtures" / "scryfall_sample.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def card_map(scryfall_cards: list[dict]) -> dict[str, Card]:
    return {c["name"]: Card.from_scryfall(c) for c in scryfall_cards}


@pytest.fixture
def mock_repo(card_map: dict[str, Card]) -> MagicMock:
    repo = MagicMock()
    repo.get_by_names.return_value = card_map
    return repo


def _entry(qty: int, name: str, section: DeckSection = DeckSection.MAIN) -> DeckEntry:
    return DeckEntry(quantity=qty, card_name=name, section=section)


def _make_deck(entries: tuple[DeckEntry, ...]) -> Deck:
    return Deck(metadata=DeckMetadata(), entries=entries, comments=())


class TestAnalyticsService:
    def test_compute_returns_deck_stats(self, mock_repo: MagicMock) -> None:
        service = AnalyticsService(card_repo=mock_repo)
        deck = _make_deck((
            _entry(4, "Goblin Guide"),
            _entry(4, "Lightning Bolt"),
        ))
        stats = service.compute(deck)
        assert isinstance(stats, DeckStats)
        assert stats.mainboard_count == 8
        mock_repo.get_by_names.assert_called_once()

    def test_cache_hit(self, mock_repo: MagicMock) -> None:
        """Second call with same deck should not query repo again."""
        service = AnalyticsService(card_repo=mock_repo)
        deck = _make_deck((
            _entry(4, "Goblin Guide"),
            _entry(4, "Lightning Bolt"),
        ))
        stats1 = service.compute(deck)
        stats2 = service.compute(deck)
        assert stats1 is stats2
        assert mock_repo.get_by_names.call_count == 1

    def test_cache_invalidation(self, mock_repo: MagicMock) -> None:
        service = AnalyticsService(card_repo=mock_repo)
        deck = _make_deck((_entry(4, "Goblin Guide"),))
        stats1 = service.compute(deck)
        service.invalidate()
        stats2 = service.compute(deck)
        assert mock_repo.get_by_names.call_count == 2
        assert stats1 == stats2

    def test_cache_miss_on_different_deck(self, mock_repo: MagicMock) -> None:
        service = AnalyticsService(card_repo=mock_repo)
        deck1 = _make_deck((_entry(4, "Goblin Guide"),))
        deck2 = _make_deck((
            _entry(4, "Goblin Guide"),
            _entry(4, "Lightning Bolt"),
        ))
        service.compute(deck1)
        service.compute(deck2)
        assert mock_repo.get_by_names.call_count == 2

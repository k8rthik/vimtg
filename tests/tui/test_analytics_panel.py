"""Unit tests for the AnalyticsPanel widget — render() called directly,
no mounting (same approach as the other embedded Static widgets)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.tui.widgets.analytics_panel import AnalyticsPanel, build_analytics_data

_DECK = (
    "// Creature\n"
    "4 Goblin Guide\n"
    "4 Eidolon of the Great Revel\n"
    "\n"
    "// Instant\n"
    "4 Lightning Bolt\n"
    "\n"
    "// Land\n"
    "20 Mountain\n"
    "2 Sacred Foundry\n"
    "\n"
    "SB: 3 Rest in Peace\n"
)


@pytest.fixture
def card_map() -> dict[str, Card]:
    path = Path(__file__).parent.parent / "fixtures" / "scryfall_sample.json"
    return {
        c["name"]: Card.from_scryfall(c) for c in json.loads(path.read_text())
    }


def _panel(card_map: dict[str, Card], deck_text: str = _DECK) -> AnalyticsPanel:
    panel = AnalyticsPanel()
    panel.data = build_analytics_data(parse_deck_text(deck_text), card_map)
    return panel


class TestBuildAnalyticsData:
    def test_zones_skip_empty(self, card_map: dict[str, Card]) -> None:
        data = build_analytics_data(parse_deck_text(_DECK), card_map)
        labels = [label for label, _ in data.zones]
        assert ("main", 34) in data.zones
        assert ("side", 3) in data.zones
        assert "maybe" not in labels  # empty zones are dropped

    def test_categories_empty_without_category_layout(
        self, card_map: dict[str, Card]
    ) -> None:
        data = build_analytics_data(parse_deck_text(_DECK), card_map)
        assert data.categories == ()

    def test_categories_present_with_layout(self, card_map: dict[str, Card]) -> None:
        deck = parse_deck_text(
            "4 Lightning Bolt  @removal\n4 Goblin Guide  @aggro\n20 Mountain\n"
        )
        data = build_analytics_data(deck, card_map)
        assert ("removal", 4) in data.categories
        assert ("aggro", 4) in data.categories
        assert ("(none)", 20) in data.categories


class TestAnalyticsPanelRender:
    def test_no_data_shows_status(self) -> None:
        panel = AnalyticsPanel()
        text = panel.render().plain
        assert "No deck data" in text

    def test_sections_render(self, card_map: dict[str, Card]) -> None:
        text = _panel(card_map).render().plain
        for heading in ("CURVE", "TYPES", "ZONES", "MANA BASE", "DRAWS"):
            assert heading in text

    def test_type_counts(self, card_map: dict[str, Card]) -> None:
        text = _panel(card_map).render().plain
        assert "Creature" in text and "8" in text
        assert "Land" in text and "22" in text

    def test_mana_base_marks(self, card_map: dict[str, Card]) -> None:
        text = _panel(card_map).render().plain
        assert "✓" in text  # red is satisfied (22 sources)

    def test_mana_base_shortfall(self, card_map: dict[str, Card]) -> None:
        deck = "4 Rest in Peace\n20 Mountain\n"  # no white sources
        text = _panel(card_map, deck).render().plain
        assert "✗" in text

    def test_cursor_card_odds(self, card_map: dict[str, Card]) -> None:
        panel = _panel(card_map)
        panel.cursor_card = ("Lightning Bolt", 4)
        text = panel.render().plain
        assert "Lightning Bolt" in text
        assert "62%" in text  # 4-of in this 34-card mainboard's opener

    def test_no_cursor_card_row_without_cursor(self, card_map: dict[str, Card]) -> None:
        text = _panel(card_map).render().plain
        assert "Lightning Bolt" not in text

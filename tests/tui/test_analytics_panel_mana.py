"""AnalyticsPanel: land hint, MDFC-aware land total, bracket section."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.tui.widgets.analytics_panel import AnalyticsPanel, build_analytics_data

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def cards(real_shape_cards: list[dict[str, Any]]) -> dict[str, Card]:
    extra = json.loads(
        (FIXTURES / "scryfall_mana_analytics.json").read_text(encoding="utf-8")
    )
    return {d["name"]: Card.from_scryfall(d) for d in real_shape_cards + extra}


def _render(cards: dict[str, Card], text: str) -> str:
    panel = AnalyticsPanel()
    panel.data = build_analytics_data(parse_deck_text(text), cards)
    return panel.render().plain


def test_mana_base_heading_excludes_mdfc_spells(cards: dict[str, Card]) -> None:
    out = _render(
        cards,
        "4 Valakut Awakening // Valakut Stoneforge\n4 Lightning Bolt\n10 Mountain\n",
    )
    assert "MANA BASE (10 lands)" in out


def test_fetches_do_not_cause_false_shortfall(cards: dict[str, Card]) -> None:
    out = _render(
        cards,
        "36 Lightning Helix\n8 Arid Mesa\n8 Mountain\n8 Plains\n",
    )
    assert "need" not in out


def test_land_hint_shown(cards: dict[str, Card]) -> None:
    out = _render(cards, "36 Lightning Helix\n24 Mountain\n")
    assert "suggested ~23 lands" in out


def test_bracket_section_for_commander_deck(cards: dict[str, Card]) -> None:
    out = _render(
        cards,
        "CMD: 1 Aurelia, the Warleader\n1 Smothering Tithe\n1 Gamble\n"
        "1 Mountain\n",
    )
    assert "COMMANDER BRACKET" in out
    assert "Game Changers 2" in out
    assert "Smothering Tithe" in out
    assert "estimated bracket 3" in out
    assert "heuristic" in out


def test_no_bracket_section_outside_commander(cards: dict[str, Card]) -> None:
    out = _render(cards, "// Format: modern\n4 Gamble\n20 Mountain\n")
    assert "COMMANDER BRACKET" not in out

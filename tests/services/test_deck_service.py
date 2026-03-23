"""Tests for DeckService — validation, open, save, new deck."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.data.deck_repository import DeckRepository, parse_deck_text
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
from vimtg.services.deck_service import DeckService


@pytest.fixture
def deck_repo() -> DeckRepository:
    return DeckRepository()


@pytest.fixture
def service(deck_repo: DeckRepository) -> DeckService:
    return DeckService(deck_repo=deck_repo)


@pytest.fixture
def valid_deck(sample_deck_path: Path, deck_repo: DeckRepository) -> Deck:
    text = deck_repo.load(sample_deck_path)
    return parse_deck_text(text)


# --- open / save ---


def test_open_deck(service: DeckService, sample_deck_path: Path) -> None:
    text, deck = service.open_deck(sample_deck_path)
    assert isinstance(text, str)
    assert isinstance(deck, Deck)
    assert deck.metadata.name == "Burn"
    assert len(deck.entries) > 0


def test_save_deck(service: DeckService, tmp_path: Path) -> None:
    content = "// Deck: Test\n4 Lightning Bolt\n"
    out = tmp_path / "test.deck"
    service.save_deck(content, out)
    loaded = out.read_text(encoding="utf-8")
    assert loaded == content


# --- new deck ---


def test_new_deck(service: DeckService) -> None:
    text = service.new_deck(name="Dragons", fmt="standard", author="alice")
    assert "// Deck: Dragons" in text
    assert "// Format: standard" in text
    assert "// Author: alice" in text


def test_new_deck_parseable(service: DeckService) -> None:
    text = service.new_deck(name="Test", fmt="legacy")
    deck = parse_deck_text(text)
    assert deck.metadata.name == "Test"
    assert deck.metadata.format == "legacy"


# --- validation ---


def test_validate_valid_deck(service: DeckService, valid_deck: Deck) -> None:
    errors = service.validate(valid_deck)
    assert errors == [], f"Expected no errors, got: {errors}"


def test_validate_over_four_copies(service: DeckService) -> None:
    entries = (
        DeckEntry(quantity=5, card_name="Lightning Bolt", section=DeckSection.MAIN),
    )
    deck = Deck(
        metadata=DeckMetadata(),
        entries=entries,
        comments=(),
    )
    errors = service.validate(deck)
    warnings = [e for e in errors if e.level == "warning" and "More than 4" in e.message]
    assert len(warnings) == 1
    assert "Lightning Bolt" in warnings[0].message


def test_validate_basic_land_exempt(service: DeckService) -> None:
    entries = (
        DeckEntry(quantity=8, card_name="Mountain", section=DeckSection.MAIN),
    )
    deck = Deck(
        metadata=DeckMetadata(),
        entries=entries,
        comments=(),
    )
    errors = service.validate(deck)
    four_copy_warnings = [e for e in errors if "More than 4" in e.message]
    assert four_copy_warnings == []


def test_validate_zero_quantity(service: DeckService) -> None:
    entries = (
        DeckEntry(quantity=0, card_name="Lightning Bolt", section=DeckSection.MAIN),
    )
    deck = Deck(
        metadata=DeckMetadata(),
        entries=entries,
        comments=(),
    )
    errors = service.validate(deck)
    qty_errors = [e for e in errors if e.level == "error" and "Invalid quantity" in e.message]
    assert len(qty_errors) == 1


def test_validate_small_mainboard(service: DeckService) -> None:
    entries = (
        DeckEntry(quantity=4, card_name="Lightning Bolt", section=DeckSection.MAIN),
    )
    deck = Deck(
        metadata=DeckMetadata(),
        entries=entries,
        comments=(),
    )
    errors = service.validate(deck)
    small_warnings = [e for e in errors if "minimum 60" in e.message]
    assert len(small_warnings) == 1


def test_validate_large_sideboard(service: DeckService) -> None:
    entries = (
        DeckEntry(quantity=16, card_name="Rest in Peace", section=DeckSection.SIDEBOARD),
    )
    deck = Deck(
        metadata=DeckMetadata(),
        entries=entries,
        comments=(),
    )
    errors = service.validate(deck)
    side_warnings = [e for e in errors if "maximum 15" in e.message]
    assert len(side_warnings) == 1

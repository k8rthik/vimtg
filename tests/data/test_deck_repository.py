"""Tests for the deck file parser, serializer, and repository."""

from pathlib import Path

import pytest

from vimtg.data.deck_repository import (
    DeckRepository,
    parse_deck_text,
    serialize_deck,
)
from vimtg.domain.deck import DeckSection


@pytest.fixture
def burn_deck_text(sample_deck_path: Path) -> str:
    return sample_deck_path.read_text(encoding="utf-8")


class TestParseSampleDeck:
    def test_parse_sample_deck(self, burn_deck_text: str) -> None:
        deck = parse_deck_text(burn_deck_text)
        mainboard = deck.mainboard()
        sideboard = deck.sideboard()
        assert len(mainboard) == 15
        assert len(sideboard) == 7

    def test_parse_total_cards(self, burn_deck_text: str) -> None:
        deck = parse_deck_text(burn_deck_text)
        main_total = sum(e.quantity for e in deck.mainboard())
        side_total = sum(e.quantity for e in deck.sideboard())
        assert main_total == 60
        assert side_total == 15
        assert deck.total_cards() == 75

    def test_parse_metadata(self, burn_deck_text: str) -> None:
        deck = parse_deck_text(burn_deck_text)
        assert deck.metadata.name == "Burn"
        assert deck.metadata.format == "modern"
        assert deck.metadata.author == "test"

    def test_parse_comments_preserved(self, burn_deck_text: str) -> None:
        deck = parse_deck_text(burn_deck_text)
        comment_texts = [c.text for c in deck.comments]
        assert "// Creatures" in comment_texts
        assert "// Spells" in comment_texts
        assert "// Lands" in comment_texts
        assert "// Sideboard" in comment_texts

    def test_parse_sideboard(self, burn_deck_text: str) -> None:
        deck = parse_deck_text(burn_deck_text)
        sideboard = deck.sideboard()
        names = {e.card_name for e in sideboard}
        assert "Rest in Peace" in names
        assert "Kor Firewalker" in names
        assert "Sanctifier en-Vec" in names
        assert all(e.section == DeckSection.SIDEBOARD for e in sideboard)

    def test_parse_card_names(self, burn_deck_text: str) -> None:
        deck = parse_deck_text(burn_deck_text)
        names = deck.unique_card_names()
        assert "Goblin Guide" in names
        assert "Lightning Bolt" in names
        assert "Mountain" in names


class TestParseEdgeCases:
    def test_parse_blank_lines(self) -> None:
        text = "\n\n4 Lightning Bolt\n\n\n"
        deck = parse_deck_text(text)
        assert len(deck.entries) == 1
        assert deck.entries[0].card_name == "Lightning Bolt"

    def test_parse_invalid_line(self) -> None:
        text = "4 Lightning Bolt\nthis is invalid\n3 Goblin Guide\n"
        deck = parse_deck_text(text)
        assert len(deck.entries) == 2

    def test_parse_empty_text(self) -> None:
        deck = parse_deck_text("")
        assert len(deck.entries) == 0
        assert deck.total_cards() == 0

    def test_parse_commander_prefix(self) -> None:
        text = "CMD: 1 Atraxa, Praetors' Voice\n"
        deck = parse_deck_text(text)
        assert len(deck.entries) == 1
        assert deck.entries[0].section == DeckSection.COMMANDER
        assert deck.entries[0].card_name == "Atraxa, Praetors' Voice"

    def test_parse_card_with_special_chars(self) -> None:
        text = "1 Jotun Grunt\n1 Fire // Ice\n1 Lim-Dul's Vault\n"
        deck = parse_deck_text(text)
        assert len(deck.entries) == 3
        names = {e.card_name for e in deck.entries}
        assert "Fire // Ice" in names
        assert "Lim-Dul's Vault" in names


class TestSerialize:
    def test_serialize_produces_valid_deck(
        self, burn_deck_text: str
    ) -> None:
        original = parse_deck_text(burn_deck_text)
        serialized = serialize_deck(original)
        reparsed = parse_deck_text(serialized)
        assert reparsed.metadata.name == original.metadata.name
        assert reparsed.metadata.format == original.metadata.format
        assert reparsed.metadata.author == original.metadata.author
        assert len(reparsed.mainboard()) == len(original.mainboard())
        assert len(reparsed.sideboard()) == len(original.sideboard())
        assert reparsed.total_cards() == original.total_cards()
        assert reparsed.unique_card_names() == original.unique_card_names()

    def test_serialize_empty_deck(self) -> None:
        deck = parse_deck_text("")
        serialized = serialize_deck(deck)
        reparsed = parse_deck_text(serialized)
        assert reparsed.total_cards() == 0

    def test_serialize_sideboard_prefix(self) -> None:
        text = "SB: 2 Rest in Peace\n"
        deck = parse_deck_text(text)
        serialized = serialize_deck(deck)
        assert "SB: 2 Rest in Peace" in serialized

    def test_serialize_metadata(self) -> None:
        text = "// Deck: MyDeck\n// Format: standard\n4 Lightning Bolt\n"
        deck = parse_deck_text(text)
        serialized = serialize_deck(deck)
        assert "// Deck: MyDeck" in serialized
        assert "// Format: standard" in serialized


class TestDeckRepository:
    def test_load_and_save(
        self, tmp_path: Path, burn_deck_text: str
    ) -> None:
        repo = DeckRepository()
        deck_path = tmp_path / "test.deck"
        repo.save(deck_path, burn_deck_text)
        loaded = repo.load(deck_path)
        assert loaded == burn_deck_text

    def test_list_decks(self, tmp_path: Path) -> None:
        repo = DeckRepository()
        (tmp_path / "a.deck").write_text("4 Bolt\n")
        (tmp_path / "b.deck").write_text("4 Guide\n")
        (tmp_path / "c.txt").write_text("not a deck\n")
        decks = repo.list_decks(tmp_path)
        assert len(decks) == 2
        assert all(p.suffix == ".deck" for p in decks)

    def test_exists(self, tmp_path: Path) -> None:
        repo = DeckRepository()
        deck_path = tmp_path / "test.deck"
        assert not repo.exists(deck_path)
        deck_path.write_text("4 Bolt\n")
        assert repo.exists(deck_path)

    def test_save_atomic(self, tmp_path: Path) -> None:
        """Verify save writes atomically (no .tmp file left behind)."""
        repo = DeckRepository()
        deck_path = tmp_path / "test.deck"
        repo.save(deck_path, "4 Lightning Bolt\n")
        assert deck_path.exists()
        tmp_file = deck_path.with_suffix(".tmp")
        assert not tmp_file.exists()

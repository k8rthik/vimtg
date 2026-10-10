"""Companion-in-sideboard counting, Oathbreaker Signature Spells, and
format names shared by search and validation (aliases, case, the Arena
formats)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.analytics import is_commander_deck
from vimtg.domain.card import Card
from vimtg.domain.formats import (
    FORMAT_RULES,
    SCRYFALL_FORMATS,
    get_format_rules,
    normalize_format,
)
from vimtg.domain.search import LegalityMatch, parse_search
from vimtg.domain.validation import ValidationError, validate_deck

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def cards() -> dict[str, Card]:
    raw = json.loads((FIXTURES / "scryfall_validation.json").read_text(encoding="utf-8"))
    return {c.name: c for c in (Card.from_scryfall(d) for d in raw)}


def _errors(errs: list[ValidationError]) -> list[str]:
    return [e.message for e in errs if e.level == "error"]


def _warnings(errs: list[ValidationError]) -> list[str]:
    return [e.message for e in errs if e.level == "warning"]


# ── (d) companion counts toward the 15-card sideboard ────────────


class TestCompanionSideboard:
    def test_companion_plus_full_sideboard_is_sixteen(
        self, cards: dict[str, Card]
    ) -> None:
        deck = parse_deck_text(
            "60 Island\nSB: 15 Island\nCMP: 1 Lurrus of the Dream-Den\n"
        )
        errs = validate_deck(deck, cards, "modern")
        assert any(
            "Sideboard has 16 cards including the companion" in m
            and "maximum 15" in m
            for m in _errors(errs)
        )

    def test_companion_plus_fourteen_is_legal(self, cards: dict[str, Card]) -> None:
        deck = parse_deck_text(
            "60 Island\nSB: 14 Island\nCMP: 1 Lurrus of the Dream-Den\n"
        )
        assert not any("Sideboard" in m for m in _errors(validate_deck(deck, cards, "modern")))

    def test_companion_already_in_sideboard_not_counted_twice(
        self, cards: dict[str, Card]
    ) -> None:
        deck = parse_deck_text(
            "60 Island\nSB: 14 Island\nSB: 1 Lurrus of the Dream-Den\n"
            "CMP: 1 Lurrus of the Dream-Den\n"
        )
        assert not any("Sideboard" in m for m in _errors(validate_deck(deck, cards, "modern")))

    def test_no_format_warns_too(self, cards: dict[str, Card]) -> None:
        deck = parse_deck_text(
            "60 Island\nSB: 15 Island\nCMP: 1 Lurrus of the Dream-Den\n"
        )
        assert any(
            "16 cards including the companion" in m
            for m in _warnings(validate_deck(deck, cards, ""))
        )

    def test_commander_companion_is_outside_the_deck(
        self, cards: dict[str, Card]
    ) -> None:
        deck = parse_deck_text(
            "CMD: 1 Atraxa, Praetors' Voice\n99 Wastes\nCMP: 1 Lurrus of the Dream-Den\n"
        )
        assert not any("Sideboard" in m for m in _errors(validate_deck(deck, cards, "commander")))


# ── (e) Oathbreaker needs its Signature Spell ────────────────────


class TestSignatureSpell:
    def test_oathbreaker_without_signature_spell_errors(
        self, cards: dict[str, Card]
    ) -> None:
        deck = parse_deck_text("CMD: 1 Jace, the Mind Sculptor\n59 Island\n")
        errs = _errors(validate_deck(deck, cards, "oathbreaker"))
        assert any("0 Signature Spell" in m for m in errs)

    def test_with_signature_spell_passes(self, cards: dict[str, Card]) -> None:
        deck = parse_deck_text(
            "CMD: 1 Jace, the Mind Sculptor\nCMD: 1 Counterspell\n58 Island\n"
        )
        assert _errors(validate_deck(deck, cards, "oathbreaker")) == []

    def test_brawl_has_no_signature_spell(self, cards: dict[str, Card]) -> None:
        deck = parse_deck_text("CMD: 1 Teferi, Temporal Archmage\n99 Island\n")
        assert not any(
            "Signature" in m for m in _errors(validate_deck(deck, cards, "brawl"))
        )


# ── (f) one format vocabulary ────────────────────────────────────


class TestFormatNames:
    @pytest.mark.parametrize(
        ("typed", "key"),
        [
            ("EDH", "commander"),
            ("edh", "commander"),
            ("Commander", "commander"),
            ("historicbrawl", "brawl"),
            ("Historic Brawl", "brawl"),
            ("Standard Brawl", "standardbrawl"),
            ("PDH", "paupercommander"),
            ("Pauper Commander", "paupercommander"),
            ("Duel Commander", "duel"),
            (" Modern ", "modern"),
            ("", ""),
        ],
    )
    def test_normalize(self, typed: str, key: str) -> None:
        assert normalize_format(typed) == key

    def test_header_alias_validates_like_the_key(self, cards: dict[str, Card]) -> None:
        deck = parse_deck_text("// Format: EDH\nCMD: 1 Atraxa, Praetors' Voice\n98 Wastes\n")
        errs = validate_deck(deck, cards, deck.metadata.format)
        assert not any("Unknown format" in m for m in _warnings(errs))
        assert any("requires exactly 100" in m for m in _errors(errs))

    def test_historicbrawl_checks_brawl_legality(self, cards: dict[str, Card]) -> None:
        rules = get_format_rules("historicbrawl")
        assert rules is not None and rules.name == "brawl"

    def test_search_and_validation_agree(self) -> None:
        for typed in ("EDH", "pdh", "Historic Brawl", "explorer", "Gladiator"):
            node = parse_search(f'f:"{typed}"')
            assert isinstance(node, LegalityMatch)
            assert node.format == normalize_format(typed)
        # every validated format is a search format too
        assert set(FORMAT_RULES) <= SCRYFALL_FORMATS

    def test_commander_alias_gets_bracket(self) -> None:
        assert is_commander_deck(parse_deck_text("// Format: EDH\n1 Sol Ring\n"))

    def test_unknown_still_warns(self, cards: dict[str, Card]) -> None:
        errs = validate_deck(parse_deck_text("60 Island\n"), cards, "kitchen-table")
        assert any("Unknown format" in m for m in _warnings(errs))


class TestArenaFormats:
    @pytest.mark.parametrize("fmt", ["explorer", "alchemy", "historic", "timeless"])
    def test_sixty_card_arena_formats(self, fmt: str) -> None:
        rules = get_format_rules(fmt)
        assert rules is not None
        assert (rules.min_deck_size, rules.max_sideboard, rules.copy_limit) == (60, 15, 4)
        assert rules.allows_sideboard and not rules.requires_commander

    def test_gladiator(self, cards: dict[str, Card]) -> None:
        rules = get_format_rules("Gladiator")
        assert rules is not None
        assert rules.min_deck_size == 100 and rules.copy_limit == 1
        assert not rules.allows_sideboard and not rules.requires_commander
        deck = parse_deck_text("2 Counterspell\n98 Island\nSB: 1 Ponder\n")
        errs = _errors(validate_deck(deck, cards, "gladiator"))
        assert any("Counterspell: 2 copies" in m for m in errs)
        assert any("gladiator decks have no sideboard" in m for m in errs)
        short = validate_deck(parse_deck_text("60 Island\n"), cards, "gladiator")
        assert any("minimum 100" in m for m in _warnings(short))

    def test_explorer_legality_checked(self, cards: dict[str, Card]) -> None:
        # Was: "Unknown format: explorer" and no legality check at all.
        spell = replace(
            cards["Counterspell"],
            legalities={**cards["Counterspell"].legalities, "explorer": "not_legal"},
        )
        deck = parse_deck_text("4 Counterspell\n56 Island\n")
        errs = validate_deck(deck, {**cards, "Counterspell": spell}, "Explorer")
        assert not any("Unknown format" in m for m in _warnings(errs))
        assert any("Counterspell is not legal in explorer" in m for m in _errors(errs))

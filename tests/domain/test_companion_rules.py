"""Companion-zone validation — format-agnostic, like the zone itself."""

from __future__ import annotations

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.domain.validation import validate_deck


def _card(
    name: str,
    type_line: str = "Legendary Creature — Cat Nightmare",
    keywords: tuple[str, ...] = (),
    oracle_text: str = "",
) -> Card:
    return Card.from_scryfall({
        "id": f"id-{name.lower().replace(' ', '-')}",
        "name": name,
        "type_line": type_line,
        "keywords": list(keywords),
        "oracle_text": oracle_text,
    })


def _resolved(*cards: Card) -> dict[str, Card]:
    return {c.name: c for c in cards}


class TestCompanionCount:
    def test_single_companion_is_clean(self):
        deck = parse_deck_text("CMP: 1 Lurrus\n60 Forest\n")
        errors = validate_deck(deck)
        assert not any("ompanion" in e.message for e in errors)

    def test_two_companions_is_error(self):
        deck = parse_deck_text("CMP: 1 Lurrus\nCMP: 1 Jegantha\n60 Forest\n")
        errors = validate_deck(deck)
        assert any("2 companions (maximum 1)" in e.message for e in errors)

    def test_companion_quantity_must_be_1(self):
        deck = parse_deck_text("CMP: 2 Lurrus\n60 Forest\n")
        errors = validate_deck(deck)
        assert any(
            "Companion Lurrus: quantity must be 1" in e.message
            for e in errors
        )

    def test_check_runs_in_formatted_validation_too(self):
        deck = parse_deck_text(
            "// Format: commander\n"
            "CMD: 1 Atraxa\n99 Forest\nCMP: 2 Lurrus\n"
        )
        errors = validate_deck(deck, fmt="commander")
        assert any("quantity must be 1" in e.message for e in errors)


class TestCompanionAbility:
    def test_resolved_companion_with_keyword_is_clean(self):
        deck = parse_deck_text("CMP: 1 Lurrus of the Dream-Den\n60 Forest\n")
        resolved = _resolved(
            _card("Lurrus of the Dream-Den", keywords=("Companion", "Lifelink")),
            _card("Forest", type_line="Basic Land — Forest"),
        )
        errors = validate_deck(deck, resolved)
        assert not any("is not a companion" in e.message for e in errors)

    def test_non_companion_card_warns(self):
        deck = parse_deck_text("CMP: 1 Grizzly Bears\n60 Forest\n")
        resolved = _resolved(
            _card("Grizzly Bears", type_line="Creature — Bear"),
            _card("Forest", type_line="Basic Land — Forest"),
        )
        errors = validate_deck(deck, resolved)
        warn = [e for e in errors if "is not a companion" in e.message]
        assert warn and warn[0].level == "warning"

    def test_oracle_text_fallback_when_keywords_missing(self):
        deck = parse_deck_text("CMP: 1 Umori, the Collector\n60 Forest\n")
        resolved = _resolved(
            _card(
                "Umori, the Collector",
                oracle_text="Companion — Each nonland card...",
            ),
            _card("Forest", type_line="Basic Land — Forest"),
        )
        errors = validate_deck(deck, resolved)
        assert not any("is not a companion" in e.message for e in errors)


class TestCompanionOutsideDeck:
    def test_companion_not_counted_in_commander_100(self):
        deck = parse_deck_text(
            "CMD: 1 Atraxa\n99 Forest\nCMP: 1 Lurrus\n"
        )
        errors = validate_deck(deck, fmt="commander")
        assert not any("requires exactly" in e.message for e in errors)

    def test_companion_not_counted_in_copy_limit(self):
        deck = parse_deck_text(
            "// Format: modern\n4 Mishra's Bauble\n56 Forest\n"
            "CMP: 1 Mishra's Bauble\n"
        )
        errors = validate_deck(deck, fmt="modern")
        assert not any("copies" in e.message for e in errors)

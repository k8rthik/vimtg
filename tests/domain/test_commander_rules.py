"""Commander-format validation: deck size, sideboard, copies, partners."""

from __future__ import annotations

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.domain.validation import validate_deck


def _card(
    name: str,
    type_line: str = "Legendary Creature — Angel",
    color_identity: tuple[str, ...] = (),
    keywords: tuple[str, ...] = (),
    oracle_text: str = "",
    legalities: dict[str, str] | None = None,
) -> Card:
    return Card.from_scryfall({
        "id": f"id-{name.lower().replace(' ', '-').replace(',', '')}",
        "name": name,
        "type_line": type_line,
        "color_identity": list(color_identity),
        "keywords": list(keywords),
        "oracle_text": oracle_text,
        "legalities": legalities or {},
    })


def _resolved(*cards: Card) -> dict[str, Card]:
    return {c.name: c for c in cards}


def _messages(errors) -> str:
    return " | ".join(e.message for e in errors)


class TestDeckSize:
    def test_commander_counts_toward_exact_100(self):
        deck = parse_deck_text("CMD: 1 Atraxa\n99 Forest\n")
        errors = validate_deck(deck, fmt="commander")
        assert not any("requires exactly" in e.message for e in errors)

    def test_99_cards_plus_commander_missing_one_errors(self):
        deck = parse_deck_text("CMD: 1 Atraxa\n98 Forest\n")
        errors = validate_deck(deck, fmt="commander")
        assert any(
            "99 cards" in e.message and "exactly 100" in e.message
            for e in errors
        )

    def test_maybeboard_does_not_count(self):
        deck = parse_deck_text("CMD: 1 Atraxa\n99 Forest\nMB: 4 Opt\n")
        errors = validate_deck(deck, fmt="commander")
        assert not any("requires exactly" in e.message for e in errors)


class TestSideboard:
    def test_sideboard_entries_are_errors(self):
        deck = parse_deck_text("CMD: 1 Atraxa\n99 Forest\nSB: 1 Opt\n")
        errors = validate_deck(deck, fmt="commander")
        sb = [e for e in errors if "no sideboard" in e.message]
        assert sb and sb[0].level == "error"

    def test_maybeboard_is_allowed(self):
        deck = parse_deck_text("CMD: 1 Atraxa\n99 Forest\nMB: 1 Opt\n")
        errors = validate_deck(deck, fmt="commander")
        assert not any("Opt" in e.message for e in errors)


class TestSingleton:
    def test_commander_copy_counts_toward_singleton(self):
        # CMD: Atraxa plus a mainboard Atraxa = 2 copies of a 1-max card
        deck = parse_deck_text(
            "CMD: 1 Atraxa, Praetors' Voice\n"
            "1 Atraxa, Praetors' Voice\n"
            "98 Forest\n"
        )
        errors = validate_deck(deck, fmt="commander")
        assert any(
            "Atraxa" in e.message and "2 copies" in e.message for e in errors
        )

    def test_basic_lands_exempt(self):
        deck = parse_deck_text("CMD: 1 Atraxa\n99 Forest\n")
        errors = validate_deck(deck, fmt="commander")
        assert not any("copies" in e.message for e in errors)


class TestCommanderEntries:
    def test_missing_commander_is_error(self):
        deck = parse_deck_text("// Format: commander\n100 Forest\n")
        errors = validate_deck(deck, fmt="commander")
        assert any("No commander" in e.message for e in errors)

    def test_commander_quantity_must_be_1(self):
        deck = parse_deck_text("CMD: 2 Atraxa\n98 Forest\n")
        errors = validate_deck(deck, fmt="commander")
        assert any("quantity must be 1" in e.message for e in errors)

    def test_three_commanders_is_error(self):
        deck = parse_deck_text(
            "CMD: 1 A\nCMD: 1 B\nCMD: 1 C\n97 Forest\n"
        )
        errors = validate_deck(deck, fmt="commander")
        assert any("maximum 2" in e.message for e in errors)

    def test_non_legendary_commander_is_error(self):
        deck = parse_deck_text("CMD: 1 Grizzly Bears\n99 Forest\n")
        resolved = _resolved(
            _card("Grizzly Bears", type_line="Creature — Bear"),
            _card("Forest", type_line="Basic Land — Forest"),
        )
        errors = validate_deck(deck, resolved, fmt="commander")
        assert any("not legendary" in e.message for e in errors)


class TestPartnerPairs:
    def _validate_pair(self, a: Card, b: Card):
        deck = parse_deck_text(
            f"CMD: 1 {a.name}\nCMD: 1 {b.name}\n98 Forest\n"
        )
        resolved = _resolved(
            a, b, _card("Forest", type_line="Basic Land — Forest")
        )
        return validate_deck(deck, resolved, fmt="commander")

    def test_two_partners_do_not_warn(self):
        a = _card("Thrasios, Triton Hero", keywords=("Partner",))
        b = _card("Tymna the Weaver", keywords=("Partner",))
        errors = self._validate_pair(a, b)
        assert not any("legal commander pair" in e.message for e in errors)

    def test_background_pairing_does_not_warn(self):
        a = _card(
            "Wilson, Refined Grizzly",
            oracle_text="Choose a Background",
        )
        b = _card(
            "Raised by Giants",
            type_line="Legendary Enchantment — Background",
        )
        errors = self._validate_pair(a, b)
        assert not any("legal commander pair" in e.message for e in errors)

    def test_two_non_partners_warn(self):
        a = _card("Atraxa, Praetors' Voice")
        b = _card("Urza, Lord High Artificer")
        errors = self._validate_pair(a, b)
        pair = [e for e in errors if "legal commander pair" in e.message]
        assert pair and pair[0].level == "warning"


class TestColorIdentity:
    def test_partner_identities_combine(self):
        a = _card("Thrasios, Triton Hero", color_identity=("G", "U"),
                  keywords=("Partner",))
        b = _card("Tymna the Weaver", color_identity=("W", "B"),
                  keywords=("Partner",))
        spell = _card("Anguished Unmaking", type_line="Instant",
                      color_identity=("W", "B"))
        deck = parse_deck_text(
            "CMD: 1 Thrasios, Triton Hero\n"
            "CMD: 1 Tymna the Weaver\n"
            "1 Anguished Unmaking\n"
            "97 Forest\n"
        )
        resolved = _resolved(
            a, b, spell, _card("Forest", type_line="Basic Land — Forest")
        )
        errors = validate_deck(deck, resolved, fmt="commander")
        assert not any("color identity" in e.message for e in errors)

    def test_off_color_card_is_error(self):
        commander = _card("Urza, Lord High Artificer", color_identity=("U",))
        spell = _card("Lightning Bolt", type_line="Instant",
                      color_identity=("R",))
        deck = parse_deck_text(
            "CMD: 1 Urza, Lord High Artificer\n"
            "1 Lightning Bolt\n98 Island\n"
        )
        resolved = _resolved(
            commander, spell, _card("Island", type_line="Basic Land — Island")
        )
        errors = validate_deck(deck, resolved, fmt="commander")
        assert any("color identity" in e.message for e in errors)

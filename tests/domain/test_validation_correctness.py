"""Validation correctness: commander eligibility, companion identity,
oracle-text copy limits, sideboard limits, unknown cards, format table.

Cards come from a Scryfall-shaped fixture so the checks run against the
same data the card database stores.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.domain.formats import FORMAT_RULES, get_format_rules
from vimtg.domain.validation import UNKNOWN_CARD, ValidationError, validate_deck

FIXTURE = Path(__file__).parent.parent / "fixtures" / "scryfall_validation.json"


@pytest.fixture(scope="module")
def cards() -> dict[str, Card]:
    with open(FIXTURE, encoding="utf-8") as f:
        return {c.name: c for c in (Card.from_scryfall(d) for d in json.load(f))}


def _validate(
    text: str, cards: dict[str, Card], fmt: str
) -> list[ValidationError]:
    return validate_deck(parse_deck_text(text), cards, fmt)


def _errors(errs: list[ValidationError]) -> list[str]:
    return [e.message for e in errs if e.level == "error"]


def _warnings(errs: list[ValidationError]) -> list[str]:
    return [e.message for e in errs if e.level == "warning"]


def _has(msgs: list[str], *needles: str) -> bool:
    return any(all(n in m for n in needles) for m in msgs)


def _cmd_deck(
    *commanders: str, main: int | None = None, extra: str = "",
    land: str = "Wastes",
) -> str:
    lines = [f"CMD: 1 {c}" for c in commanders]
    filler = (100 - len(commanders)) if main is None else main
    return "\n".join(lines) + f"\n{filler} {land}\n{extra}"


# --- (a) commander eligibility ---------------------------------------


class TestCommanderEligibility:
    def test_legendary_artifact_is_not_a_commander(self, cards):
        errs = _validate(_cmd_deck("The One Ring"), cards, "commander")
        assert _has(_errors(errs), "The One Ring", "can't be your commander")

    def test_legendary_creature_is_a_commander(self, cards):
        errs = _validate(_cmd_deck("Atraxa, Praetors' Voice"), cards, "commander")
        assert not _has(_errors(errs), "commander")

    def test_can_be_your_commander_text_is_eligible(self, cards):
        errs = _validate(
            _cmd_deck("Teferi, Temporal Archmage"), cards, "commander"
        )
        assert not _has(_errors(errs), "can't be your commander")

    def test_creature_while_off_battlefield_is_eligible(self, cards):
        # Grist is a 1/1 Insect creature card everywhere but the battlefield
        errs = _validate(_cmd_deck("Grist, the Hunger Tide"), cards, "commander")
        assert not _has(_errors(errs), "can't be your commander")

    def test_plain_planeswalker_is_not_a_commander(self, cards):
        errs = _validate(_cmd_deck("Jace, the Mind Sculptor"), cards, "commander")
        assert _has(_errors(errs), "Jace", "can't be your commander")

    def test_planeswalker_is_a_brawl_commander(self, cards):
        errs = _validate(_cmd_deck("Jace, the Mind Sculptor"), cards, "brawl")
        assert not _has(_errors(errs), "can't be your commander")

    def test_legendary_vehicle_is_a_commander(self, cards):
        # CR 903.3 (Edge of Eternities update): Vehicles can lead a deck
        errs = _validate(_cmd_deck("Parhelion II"), cards, "commander")
        assert not _has(_errors(errs), "can't be your commander")

    def test_legendary_spacecraft_needs_pt_box(self):
        def ship(name: str, pt: bool) -> Card:
            data = {
                "id": f"id-{name}", "name": name,
                "type_line": "Legendary Artifact — Spacecraft",
                "oracle_text": "Station", "color_identity": [],
            }
            if pt:
                data |= {"power": "5", "toughness": "5"}
            return Card.from_scryfall(data)

        resolved = {"Big Ship": ship("Big Ship", True),
                    "Small Ship": ship("Small Ship", False)}
        ok = validate_deck(parse_deck_text(_cmd_deck("Big Ship")), resolved, "commander")
        bad = validate_deck(parse_deck_text(_cmd_deck("Small Ship")), resolved, "commander")
        assert not _has(_errors(ok), "can't be your commander")
        assert _has(_errors(bad), "Small Ship", "can't be your commander")

    def test_lone_background_is_an_error(self, cards):
        errs = _validate(_cmd_deck("Raised by Giants"), cards, "commander")
        assert _has(_errors(errs), "Raised by Giants", "Choose a Background")

    def test_background_with_choose_a_background_is_clean(self, cards):
        errs = _validate(
            _cmd_deck("Wilson, Refined Grizzly", "Raised by Giants"),
            cards, "commander",
        )
        assert _errors(errs) == []
        assert not _has(_warnings(errs), "commander pair")

    def test_background_with_partner_creature_is_an_error(self, cards):
        errs = _validate(
            _cmd_deck("Tymna the Weaver", "Raised by Giants"), cards, "commander"
        )
        assert _has(_errors(errs), "Raised by Giants", "Choose a Background")

    def test_partner_pair_is_clean(self, cards):
        errs = _validate(
            _cmd_deck("Tymna the Weaver", "Thrasios, Triton Hero"),
            cards, "commander",
        )
        assert not _has(_warnings(errs), "commander pair")

    def test_partner_with_non_partner_stays_a_warning(self, cards):
        errs = _validate(
            _cmd_deck("Tymna the Weaver", "Atraxa, Praetors' Voice"),
            cards, "commander",
        )
        assert _has(_warnings(errs), "may not be a legal commander pair")
        assert not _has(_errors(errs), "commander pair")

    def test_doctors_companion_pairs_with_a_doctor(self):
        doctor = Card.from_scryfall({
            "id": "d", "name": "The Tenth Doctor",
            "type_line": "Legendary Creature — Time Lord Doctor",
            "color_identity": ["R", "G", "U"],
        })
        rose = Card.from_scryfall({
            "id": "r", "name": "Rose Tyler",
            "type_line": "Legendary Creature — Human",
            "keywords": ["Doctor's companion"], "color_identity": ["W"],
        })
        resolved = {c.name: c for c in (doctor, rose)}
        errs = validate_deck(
            parse_deck_text(_cmd_deck("The Tenth Doctor", "Rose Tyler")),
            resolved, "commander",
        )
        assert not _has(_warnings(errs), "commander pair")

    def test_pauper_commander_allows_nonlegendary_creature(self, cards):
        errs = _validate(_cmd_deck("Murmuring Mystic"), cards, "paupercommander")
        assert not _has(_errors(errs), "Murmuring Mystic")

    def test_pauper_commander_restricted_card_in_the_99_is_flagged(self, cards):
        # Scryfall marks uncommon creatures "restricted" in paupercommander:
        # legal as the commander only.
        errs = _validate(
            _cmd_deck("Murmuring Mystic", main=98, extra="1 Murmuring Mystic\n"),
            cards, "paupercommander",
        )
        assert _has(_errors(errs), "Murmuring Mystic", "only as the commander")


class TestOathbreaker:
    def test_oathbreaker_and_signature_spell_make_60(self, cards):
        errs = _validate(
            _cmd_deck("Jace, the Mind Sculptor", "Counterspell", main=58),
            cards, "oathbreaker",
        )
        assert _errors(errs) == []

    def test_signature_spell_outside_identity(self, cards):
        errs = _validate(
            _cmd_deck("Jace, the Mind Sculptor", "Lightning Bolt", main=58),
            cards, "oathbreaker",
        )
        assert _has(_errors(errs), "Lightning Bolt", "color identity")

    def test_creature_cannot_be_an_oathbreaker(self, cards):
        errs = _validate(
            _cmd_deck("Atraxa, Praetors' Voice", main=59), cards, "oathbreaker"
        )
        assert _has(_errors(errs), "Atraxa", "neither a planeswalker")
        assert _has(_errors(errs), "No Oathbreaker")

    def test_two_signature_spells_for_one_oathbreaker(self, cards):
        errs = _validate(
            _cmd_deck("Jace, the Mind Sculptor", "Counterspell", "Ponder", main=57),
            cards, "oathbreaker",
        )
        assert _has(_errors(errs), "2 Signature Spells")


# --- (b) companion colour identity -----------------------------------


class TestCompanionIdentity:
    def test_companion_outside_commander_identity_errors(self, cards):
        errs = _validate(
            _cmd_deck("Atraxa, Praetors' Voice", extra="CMP: 1 Jegantha, the Wellspring\n"),
            cards, "commander",
        )
        assert _has(_errors(errs), "Companion Jegantha", "color identity")

    def test_companion_inside_identity_is_clean(self, cards):
        errs = _validate(
            _cmd_deck("Atraxa, Praetors' Voice", extra="CMP: 1 Lurrus of the Dream-Den\n"),
            cards, "commander",
        )
        assert not _has(_errors(errs), "Companion")

    def test_no_identity_rule_outside_commander_formats(self, cards):
        errs = _validate(
            "60 Island\nCMP: 1 Jegantha, the Wellspring\n", cards, "modern"
        )
        assert not _has(_errors(errs), "Companion")


# --- (c) oracle-text copy limits -------------------------------------


class TestOracleCopyLimits:
    def test_any_number_in_commander(self, cards):
        errs = _validate(
            _cmd_deck("Atraxa, Praetors' Voice", main=69, extra="30 Relentless Rats\n"),
            cards, "commander",
        )
        assert not _has(_errors(errs), "Relentless Rats")

    def test_any_number_in_modern(self, cards):
        errs = _validate("20 Relentless Rats\n40 Island\n", cards, "modern")
        assert not _has(_errors(errs), "Relentless Rats")

    def test_up_to_seven_seven_dwarves(self, cards):
        ok = _validate("7 Seven Dwarves\n53 Island\n", cards, "modern")
        over = _validate("8 Seven Dwarves\n52 Island\n", cards, "modern")
        assert not _has(_errors(ok), "Seven Dwarves")
        assert _has(_errors(over), "Seven Dwarves", "8 copies", "max 7")

    def test_up_to_nine_nazgul_in_commander(self, cards):
        errs = _validate(
            _cmd_deck("Atraxa, Praetors' Voice", main=90, extra="9 Nazgûl\n"),
            cards, "commander",
        )
        assert not _has(_errors(errs), "Nazgûl")

    def test_ordinary_card_still_limited(self, cards):
        errs = _validate("5 Lightning Bolt\n55 Island\n", cards, "modern")
        assert _has(_errors(errs), "Lightning Bolt", "max 4")

    def test_generic_rules_respect_any_number(self, cards):
        errs = _validate("20 Relentless Rats\n40 Island\n", cards, "")
        assert not _has(_warnings(errs), "Relentless Rats")


# --- (d) sideboard limit and unknown cards ---------------------------


class TestSideboardAndUnknown:
    def test_oversized_sideboard_is_an_error(self, cards):
        errs = _validate("60 Island\nSB: 16 Forest\n", cards, "modern")
        assert _has(_errors(errs), "Sideboard has 16 cards", "maximum 15")

    def test_unknown_cards_reported_with_code(self, cards):
        errs = _validate("4 Not A Real Card\n56 Island\n", cards, "modern")
        unknown = [e for e in errs if e.code == UNKNOWN_CARD]
        assert len(unknown) == 1
        assert "Not A Real Card" in unknown[0].message

    def test_unknown_reported_even_when_nothing_resolves(self):
        deck = parse_deck_text("4 Nonsense\n56 Gibberish\n")
        errs = validate_deck(deck, {}, "modern", card_db=True)
        assert sum(e.code == UNKNOWN_CARD for e in errs) == 2

    def test_no_database_does_not_report_unknown(self):
        deck = parse_deck_text("4 Nonsense\n56 Gibberish\n")
        assert not any(
            e.code == UNKNOWN_CARD for e in validate_deck(deck, {}, "modern")
        )


# --- (e) formats table ------------------------------------------------


class TestFormatTable:
    @pytest.mark.parametrize(
        ("fmt", "exact", "copies", "sideboard"),
        [
            ("commander", 100, 1, False),
            ("brawl", 100, 1, False),
            ("standardbrawl", 60, 1, False),
            ("oathbreaker", 60, 1, False),
            ("paupercommander", 100, 1, False),
            ("duel", 100, 1, False),
            ("premodern", None, 4, True),
            ("historic", None, 4, True),
            ("timeless", None, 4, True),
            ("pauper", None, 4, True),
            ("penny", None, 4, True),
        ],
    )
    def test_rules(self, fmt, exact, copies, sideboard):
        rules = get_format_rules(fmt)
        assert rules is not None
        assert rules.exact_deck_size == exact
        assert rules.copy_limit == copies
        assert rules.allows_sideboard is sideboard
        assert rules.requires_commander is (exact is not None)
        if sideboard:
            assert rules.min_deck_size == 60
            assert rules.max_sideboard == 15

    def test_standard_brawl_size(self, cards):
        errs = _validate(_cmd_deck("Atraxa, Praetors' Voice", main=59),
                         cards, "standardbrawl")
        assert not _has(_errors(errs), "requires exactly")
        errs = _validate(_cmd_deck("Atraxa, Praetors' Voice"), cards, "standardbrawl")
        assert _has(_errors(errs), "requires exactly 60")

    def test_unknown_format_lists_supported(self):
        errs = validate_deck(parse_deck_text("60 Island\n"), fmt="kitchen-table")
        msg = next(m for m in _warnings(errs) if m.startswith("Unknown format"))
        for name in FORMAT_RULES:
            assert name in msg

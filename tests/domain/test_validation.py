"""Tests for format-aware deck validation."""

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.domain.validation import validate_deck


def _card(
    name: str,
    type_line: str = "Instant",
    color_identity: tuple[str, ...] = ("R",),
    legalities: dict[str, str] | None = None,
) -> Card:
    return Card.from_scryfall({
        "id": f"id-{name.lower().replace(' ', '-')}",
        "name": name,
        "type_line": type_line,
        "color_identity": list(color_identity),
        "legalities": legalities or {},
    })


def _resolved(*cards: Card) -> dict[str, Card]:
    return {c.name: c for c in cards}


def _errors_of(errors, level=None):
    if level is None:
        return errors
    return [e for e in errors if e.level == level]


def _messages(errors) -> str:
    return " | ".join(e.message for e in errors)


class TestGenericRules:
    def test_no_format_keeps_generic_checks(self):
        deck = parse_deck_text("4 Bolt\n")
        errors = validate_deck(deck)
        assert any("Mainboard has 4" in e.message for e in errors)

    def test_five_copies_warning_without_format(self):
        deck = parse_deck_text("5 Bolt\n" + "56 Mountain\n")
        errors = validate_deck(deck)
        assert any("More than 4 copies" in e.message for e in errors)

    def test_unknown_format_warns_and_falls_back(self):
        deck = parse_deck_text("// Format: kitchen\n60 Mountain\n")
        errors = validate_deck(deck, fmt="kitchen")
        assert any("Unknown format" in e.message for e in errors)

    def test_line_numbers_populated_for_entry_errors(self):
        deck = parse_deck_text("// Deck: X\n0 Bolt\n")
        errors = validate_deck(deck)
        bad_qty = [e for e in errors if "Invalid quantity" in e.message]
        assert bad_qty and bad_qty[0].line_number == 2


class TestResolvedLookup:
    def test_case_insensitive_resolution(self):
        deck = parse_deck_text("4 lightning bolt\n56 Mountain\n")
        resolved = _resolved(_card("Lightning Bolt"), _card("Mountain"))
        errors = validate_deck(deck, resolved)
        assert not any("not found" in e.message for e in errors)

    def test_unknown_name_warns(self):
        deck = parse_deck_text("4 Xyzzy\n")
        errors = validate_deck(deck, _resolved(_card("Bolt")))
        assert any("Card not found: Xyzzy" in e.message for e in errors)


class TestLegality:
    def test_banned_card_is_error(self):
        deck = parse_deck_text("// Format: modern\n4 Splinter Twin\n")
        resolved = _resolved(
            _card("Splinter Twin", legalities={"modern": "banned"})
        )
        errors = validate_deck(deck, resolved, fmt="modern")
        banned = [e for e in errors if "banned in modern" in e.message]
        assert banned and banned[0].level == "error"
        assert banned[0].line_number == 2

    def test_not_legal_card_is_error(self):
        deck = parse_deck_text("4 Brainstorm\n")
        resolved = _resolved(
            _card("Brainstorm", legalities={"pauper": "not_legal"})
        )
        errors = validate_deck(deck, resolved, fmt="pauper")
        assert any(
            "not legal in pauper" in e.message and e.level == "error"
            for e in errors
        )

    def test_restricted_multiple_copies_is_error(self):
        deck = parse_deck_text("2 Ancestral Recall\n")
        resolved = _resolved(
            _card("Ancestral Recall", legalities={"vintage": "restricted"})
        )
        errors = validate_deck(deck, resolved, fmt="vintage")
        assert any("restricted" in e.message and e.level == "error" for e in errors)

    def test_restricted_single_copy_ok(self):
        deck = parse_deck_text("1 Ancestral Recall\n")
        resolved = _resolved(
            _card("Ancestral Recall", legalities={"vintage": "restricted"})
        )
        errors = validate_deck(deck, resolved, fmt="vintage")
        assert not any("restricted" in e.message for e in errors)

    def test_legal_card_clean(self):
        deck = parse_deck_text("4 Bolt\n")
        resolved = _resolved(_card("Bolt", legalities={"modern": "legal"}))
        errors = validate_deck(deck, resolved, fmt="modern")
        assert not any("legal" in e.message.lower() for e in errors)

    def test_missing_legalities_skipped(self):
        deck = parse_deck_text("4 Bolt\n")
        errors = validate_deck(deck, _resolved(_card("Bolt")), fmt="modern")
        assert not any("banned" in e.message for e in errors)


class TestCopyLimit:
    def test_singleton_violation_flags_every_row(self):
        deck = parse_deck_text(
            "CMD: 1 Atraxa\n2 Sol Ring\n1 Arcane Signet\n"
        )
        errors = validate_deck(deck, fmt="commander")
        rows = [e.line_number for e in errors if "1 cop" in e.message]
        assert rows == [2]

    def test_basics_exempt_from_singleton(self):
        deck = parse_deck_text("CMD: 1 Atraxa\n30 Island\n")
        errors = validate_deck(deck, fmt="commander")
        assert not any("Island" in e.message and "cop" in e.message for e in errors)

    def test_copy_limit_counts_main_plus_sideboard(self):
        deck = parse_deck_text("3 Bolt\nSB: 2 Bolt\n")
        errors = validate_deck(deck, fmt="modern")
        offenders = [e for e in errors if "cop" in e.message and "Bolt" in e.message]
        assert {e.line_number for e in offenders} == {1, 2}
        assert all(e.level == "error" for e in offenders)


class TestDeckSize:
    def test_commander_exact_100_counts_commander(self):
        deck = parse_deck_text("CMD: 1 Atraxa\n98 Island\n")
        errors = validate_deck(deck, fmt="commander")
        assert any(
            "99" in e.message and "100" in e.message and e.level == "error"
            for e in errors
        )

    def test_commander_exactly_100_clean(self):
        deck = parse_deck_text("CMD: 1 Atraxa\n99 Island\n")
        errors = validate_deck(deck, fmt="commander")
        assert not any("100" in e.message for e in errors)

    def test_min_size_warning_for_60_card_formats(self):
        deck = parse_deck_text("40 Mountain\n")
        errors = validate_deck(deck, fmt="modern")
        assert any("minimum 60" in e.message and e.level == "warning" for e in errors)


class TestSideboard:
    def test_commander_sideboard_entries_are_errors(self):
        deck = parse_deck_text("CMD: 1 Atraxa\n99 Island\nSB: 1 Sol Ring\n")
        errors = validate_deck(deck, fmt="commander")
        sb = [e for e in errors if "no sideboard" in e.message]
        assert sb and sb[0].level == "error" and sb[0].line_number == 3

    def test_oversize_sideboard_warning(self):
        deck = parse_deck_text("60 Mountain\nSB: 16 Bolt\n")
        errors = validate_deck(deck, fmt="modern")
        assert any("Sideboard has 16" in e.message for e in errors)


class TestCommander:
    def test_missing_commander_is_deck_level_error(self):
        deck = parse_deck_text("100 Island\n")
        errors = validate_deck(deck, fmt="commander")
        missing = [e for e in errors if "No commander" in e.message]
        assert missing and missing[0].line_number is None

    def test_non_legendary_commander_is_error(self):
        deck = parse_deck_text("CMD: 1 Bolt\n99 Island\n")
        resolved = _resolved(
            _card("Bolt", type_line="Instant"), _card("Island", type_line="Basic Land")
        )
        errors = validate_deck(deck, resolved, fmt="commander")
        assert any("legendary" in e.message.lower() for e in errors)

    def test_color_identity_violation(self):
        deck = parse_deck_text("CMD: 1 Torbran\n1 Counterspell\n98 Mountain\n")
        resolved = _resolved(
            _card(
                "Torbran",
                type_line="Legendary Creature — Dwarf Noble",
                color_identity=("R",),
            ),
            _card("Counterspell", color_identity=("U",)),
            _card("Mountain", type_line="Basic Land", color_identity=("R",)),
        )
        errors = validate_deck(deck, resolved, fmt="commander")
        outside = [e for e in errors if "color identity" in e.message]
        assert outside and outside[0].line_number == 2

    def test_partner_union_identity(self):
        deck = parse_deck_text(
            "CMD: 1 Red Partner\nCMD: 1 Blue Partner\n1 Izzet Charm\n97 Island\n"
        )
        resolved = _resolved(
            _card(
                "Red Partner",
                type_line="Legendary Creature — Human",
                color_identity=("R",),
            ),
            _card(
                "Blue Partner",
                type_line="Legendary Creature — Merfolk",
                color_identity=("U",),
            ),
            _card("Izzet Charm", color_identity=("U", "R")),
            _card("Island", type_line="Basic Land", color_identity=("U",)),
        )
        errors = validate_deck(deck, resolved, fmt="commander")
        assert not any("color identity" in e.message for e in errors)

    def test_unresolved_commander_skips_commander_checks(self):
        deck = parse_deck_text("CMD: 1 Mystery\n99 Island\n")
        errors = validate_deck(deck, fmt="commander")
        assert not any("legendary" in e.message.lower() for e in errors)
        assert not any("color identity" in e.message for e in errors)


class TestMaybeboard:
    def test_maybeboard_excluded_from_deck_size(self):
        deck = parse_deck_text("60 Mountain\nMB: 10 Bolt\n")
        errors = validate_deck(deck, fmt="modern")
        assert not any("Mainboard has" in e.message for e in errors)

    def test_maybeboard_excluded_from_copy_limit(self):
        deck = parse_deck_text("4 Bolt\n56 Mountain\nMB: 4 Bolt\n")
        errors = validate_deck(deck, fmt="modern")
        assert not any("cop" in e.message and "Bolt" in e.message for e in errors)

    def test_maybeboard_banned_card_is_warning(self):
        deck = parse_deck_text("60 Mountain\nMB: 1 Splinter Twin\n")
        resolved = _resolved(
            _card("Splinter Twin", legalities={"modern": "banned"}),
            _card("Mountain", type_line="Basic Land"),
        )
        errors = validate_deck(deck, resolved, fmt="modern")
        mb = [e for e in errors if "Splinter Twin" in e.message and "banned" in e.message]
        assert mb and mb[0].level == "warning" and mb[0].line_number == 2

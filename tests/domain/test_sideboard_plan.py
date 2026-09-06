"""Tests for sideboard plans — the VS: block grammar and the domain model."""

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.deck import DeckSection
from vimtg.domain.deck_lines import (
    parse_plan_entry,
    parse_plan_header,
    zone_block_contexts,
    zone_context_at,
    zone_context_effect,
)
from vimtg.domain.sideboard_plan import (
    PlanEntry,
    SideboardPlan,
    apply_plan,
    find_plan,
    format_guide_markdown,
    plan_deltas,
    validate_plans,
)

BURN = """\
// Deck: Burn
// Format: modern

DCK:
    4 Lightning Bolt
    4 Goblin Guide
    2 Skullcrack

SB:
    3 Alpine Moon
    2 Rest in Peace
    2 Skullcrack

VS: Tron
    -4 Lightning Bolt
    -2 Skullcrack  // keep 1 on the draw
    +3 Alpine Moon
    +2 Rest in Peace  // hits their yard
    +1 Skullcrack

VS: Burn (draw)
    -2 Goblin Guide
    +2 Rest in Peace
"""


class TestGrammar:
    def test_plan_header_name(self) -> None:
        assert parse_plan_header("VS: Tron") == "Tron"
        assert parse_plan_header("vs: Burn (draw)") == "Burn (draw)"

    def test_plan_header_note_is_split_off(self) -> None:
        assert parse_plan_header("VS: Tron  // mull aggressively") == "Tron"

    def test_plan_header_requires_name(self) -> None:
        assert parse_plan_header("VS:") is None
        assert parse_plan_header("VS: ") is None

    def test_plan_header_rejects_non_headers(self) -> None:
        assert parse_plan_header("SB: 2 Duress") is None
        assert parse_plan_header("// vs Tron") is None
        assert parse_plan_header("4 Lightning Bolt") is None

    def test_plan_entry_signed(self) -> None:
        assert parse_plan_entry("    -4 Lightning Bolt") == ("-", 4, "Lightning Bolt")
        assert parse_plan_entry("+ 3 Alpine Moon") == ("+", 3, "Alpine Moon")

    def test_plan_entry_unsigned_keeps_empty_sign(self) -> None:
        assert parse_plan_entry("    2 Rest in Peace") == ("", 2, "Rest in Peace")

    def test_plan_entry_rejects_non_entries(self) -> None:
        assert parse_plan_entry("VS: Tron") is None
        assert parse_plan_entry("// note") is None
        assert parse_plan_entry("-Bolt") is None


class TestBlockContext:
    def test_vs_header_opens_a_block(self) -> None:
        lines = ["SB:", "    2 Duress", "VS: Tron", "    -2 Duress", "", "    +1 Opt"]
        assert zone_block_contexts(lines) == [None, "SB", None, "VS", None, "VS"]

    def test_vs_header_closes_a_zone_block(self) -> None:
        lines = ["SB:", "    2 Duress", "VS: Tron", "    -2 Duress"]
        assert zone_context_at(lines, 3) == "VS"
        assert zone_context_effect("VS: Tron") == "set:VS"

    def test_unindented_line_closes_a_plan_block(self) -> None:
        lines = ["VS: Tron", "    -2 Duress", "4 Opt"]
        assert zone_block_contexts(lines) == [None, "VS", None]


class TestParse:
    def test_plans_are_parsed(self) -> None:
        deck = parse_deck_text(BURN)
        assert [p.name for p in deck.plans] == ["Tron", "Burn (draw)"]
        tron = deck.plans[0]
        assert tron.line_number == 14
        assert [(e.sign, e.quantity, e.card_name) for e in tron.entries] == [
            ("-", 4, "Lightning Bolt"),
            ("-", 2, "Skullcrack"),
            ("+", 3, "Alpine Moon"),
            ("+", 2, "Rest in Peace"),
            ("+", 1, "Skullcrack"),
        ]
        assert tron.entries[1].comment == "keep 1 on the draw"
        assert tron.entries[1].line_number == 16

    def test_plan_lines_are_not_cards(self) -> None:
        deck = parse_deck_text(BURN)
        names = [(e.card_name, e.section) for e in deck.entries]
        assert ("Alpine Moon", DeckSection.MAIN) not in names
        assert deck.total_cards() == 17

    def test_header_note(self) -> None:
        deck = parse_deck_text("VS: Tron  // mull hard\n    -1 Opt\n")
        assert deck.plans[0].note == "mull hard"

    def test_unsigned_entry_is_kept_with_empty_sign(self) -> None:
        deck = parse_deck_text("4 Opt\nVS: Tron\n    2 Opt\n")
        assert deck.plans[0].entries[0].sign == ""
        assert deck.total_cards() == 4

    def test_explicit_prefix_wins_inside_a_plan_block(self) -> None:
        deck = parse_deck_text("VS: Tron\n    SB: 1 Duress\n")
        assert deck.plans[0].entries == ()
        assert deck.entries[0].section == DeckSection.SIDEBOARD

    def test_signed_line_outside_a_block_is_ignored(self) -> None:
        deck = parse_deck_text("4 Opt\n+2 Duress\n")
        assert deck.plans == ()
        assert deck.total_cards() == 4

    def test_deck_without_plans(self) -> None:
        assert parse_deck_text("4 Opt\n").plans == ()


class TestModel:
    def test_totals_and_balance(self) -> None:
        tron = parse_deck_text(BURN).plans[0]
        assert tron.out_total == 6
        assert tron.in_total == 6
        assert tron.is_balanced
        assert [e.card_name for e in tron.outs()] == ["Lightning Bolt", "Skullcrack"]
        assert [e.card_name for e in tron.ins()] == [
            "Alpine Moon", "Rest in Peace", "Skullcrack",
        ]

    def test_unbalanced(self) -> None:
        plan = SideboardPlan("x", (PlanEntry("Opt", 2, "-"), PlanEntry("Duress", 1, "+")))
        assert not plan.is_balanced

    def test_delta(self) -> None:
        assert PlanEntry("Opt", 2, "-").delta == -2
        assert PlanEntry("Opt", 2, "+").delta == 2
        assert PlanEntry("Opt", 2, "").delta == 0

    def test_find_plan_is_case_insensitive(self) -> None:
        deck = parse_deck_text(BURN)
        assert find_plan(deck, "tron") is deck.plans[0]
        assert find_plan(deck, "BURN (DRAW)") is deck.plans[1]
        assert find_plan(deck, "Mirror") is None


class TestApplyPlan:
    def test_boarded_configuration(self) -> None:
        deck = parse_deck_text(BURN)
        boarded = apply_plan(deck, deck.plans[0])
        main = {e.card_name: e.quantity for e in boarded.mainboard()}
        side = {e.card_name: e.quantity for e in boarded.sideboard()}
        assert main == {
            "Goblin Guide": 4, "Alpine Moon": 3, "Rest in Peace": 2, "Skullcrack": 1,
        }
        assert side == {"Lightning Bolt": 4, "Skullcrack": 3}
        assert boarded.total_cards() == deck.total_cards()

    def test_original_deck_is_untouched(self) -> None:
        deck = parse_deck_text(BURN)
        apply_plan(deck, deck.plans[0])
        assert deck.mainboard()[0].quantity == 4

    def test_plan_deltas(self) -> None:
        deck = parse_deck_text(BURN)
        assert plan_deltas(deck.plans[0]) == {
            ("Lightning Bolt", DeckSection.MAIN): -4,
            ("Skullcrack", DeckSection.MAIN): -2,
            ("Alpine Moon", DeckSection.SIDEBOARD): 3,
            ("Rest in Peace", DeckSection.SIDEBOARD): 2,
            ("Skullcrack", DeckSection.SIDEBOARD): 1,
        }


def _messages(errors) -> list[str]:
    return [f"{e.level}:{e.line_number}:{e.message}" for e in errors]


class TestValidatePlans:
    def test_clean_plan_has_no_issues(self) -> None:
        deck = parse_deck_text(BURN)
        assert validate_plans(deck) == []

    def test_out_card_must_be_in_mainboard(self) -> None:
        deck = parse_deck_text("4 Opt\nSB: 2 Duress\nVS: x\n    -1 Duress\n")
        msgs = _messages(validate_plans(deck))
        assert msgs == ["error:4:Duress is not in the mainboard"]

    def test_in_card_must_be_in_sideboard(self) -> None:
        deck = parse_deck_text("4 Opt\nVS: x\n    +1 Opt\n")
        msgs = _messages(validate_plans(deck))
        assert msgs == ["error:3:Opt is not in the sideboard"]

    def test_quantity_cannot_exceed_copies(self) -> None:
        deck = parse_deck_text("4 Opt\nSB: 2 Duress\nVS: x\n    -5 Opt\n    +3 Duress\n")
        msgs = _messages(validate_plans(deck))
        assert "error:4:-5 Opt: only 4 in the mainboard" in msgs
        assert "error:5:+3 Duress: only 2 in the sideboard" in msgs

    def test_missing_sign(self) -> None:
        deck = parse_deck_text("4 Opt\nVS: x\n    2 Opt\n")
        msgs = _messages(validate_plans(deck))
        assert msgs[0].startswith("error:3:")
        assert "+ or -" in msgs[0]

    def test_unbalanced_is_a_warning_on_the_header(self) -> None:
        deck = parse_deck_text("4 Opt\nSB: 2 Duress\nVS: x\n    -2 Opt\n    +1 Duress\n")
        msgs = _messages(validate_plans(deck))
        assert msgs == ["warning:3:vs x: -2 +1 (unbalanced)"]

    def test_duplicate_plan_name(self) -> None:
        deck = parse_deck_text("4 Opt\nVS: x\n    -1 Opt\nVS: X\n    -1 Opt\n")
        msgs = _messages(validate_plans(deck))
        assert "warning:4:Duplicate plan: X" in msgs

    def test_duplicate_entry(self) -> None:
        deck = parse_deck_text("4 Opt\nVS: x\n    -1 Opt\n    -1 Opt\n")
        msgs = _messages(validate_plans(deck))
        assert "warning:4:-1 Opt listed twice in vs x" in msgs

    def test_plan_in_format_without_sideboard(self) -> None:
        deck = parse_deck_text("// Format: commander\n1 Opt\nVS: x\n    -1 Opt\n")
        msgs = _messages(validate_plans(deck))
        assert msgs == ["warning:3:commander has no sideboard"]

    def test_case_insensitive_card_match(self) -> None:
        deck = parse_deck_text(
            "4 Lightning Bolt\nSB: 4 Shock\nVS: x\n    -4 lightning bolt\n    +4 shock\n"
        )
        assert validate_plans(deck) == []

    def test_validate_deck_includes_plan_checks(self) -> None:
        from vimtg.domain.validation import validate_deck

        deck = parse_deck_text("4 Opt\nVS: x\n    +1 Opt\n")
        assert any("not in the sideboard" in e.message for e in validate_deck(deck))


class TestMarkdown:
    def test_guide(self) -> None:
        text = format_guide_markdown(parse_deck_text(BURN))
        assert text.startswith("# Burn — sideboard guide\n")
        assert "## vs Tron\n" in text
        assert "- OUT: 4 Lightning Bolt, 2 Skullcrack\n" in text
        assert "- IN: 3 Alpine Moon, 2 Rest in Peace, 1 Skullcrack\n" in text
        assert "## vs Burn (draw)\n" in text

    def test_no_plans(self) -> None:
        assert format_guide_markdown(parse_deck_text("4 Opt\n")) == ""

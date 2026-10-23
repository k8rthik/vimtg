"""Card lines written without a quantity ('Lightning Bolt', '4x Shock')
are not cards; they are flagged so they are not silently dropped."""

from __future__ import annotations

from vimtg.data.card_repository import CardRepository
from vimtg.data.deck_repository import missing_quantity_lines
from vimtg.domain.validation import missing_quantity_warnings

_TEXT = (
    "// Deck: Burn\n"
    "Lightning Bolt\n"
    "4x Shock\n"
    "SB: Fire/Ice\n"
    "today I built a deck\n"
    "4 Mountain\n"
    "DCK:\n"
    "    2X Lightning Bolt\n"
    "VS: Control\n"
    "    Lightning Bolt\n"
)


def _messages(known: object) -> dict[int, str]:
    warnings = missing_quantity_warnings(missing_quantity_lines(_TEXT), known)  # type: ignore[arg-type]
    assert all(w.level == "warning" for w in warnings)
    return {w.line_number or 0: w.message for w in warnings}


def test_known_card_names_without_a_quantity_are_flagged(
    real_shape_repo: CardRepository,
) -> None:
    known = real_shape_repo.get_by_names([m.card_name for m in missing_quantity_lines(_TEXT)])
    assert _messages(known) == {
        2: "not a card line: add a quantity (1 Lightning Bolt)",
        3: "not a card line: drop the x (4 Shock)",
        4: "not a card line: add a quantity (SB: 1 Fire/Ice)",
        8: "not a card line: drop the x (2 Lightning Bolt)",
    }


def test_without_card_data_only_the_nx_shape_is_flagged() -> None:
    assert _messages(None) == {
        3: "not a card line: drop the x (4 Shock)",
        8: "not a card line: drop the x (2 Lightning Bolt)",
    }


def test_plan_block_lines_are_left_to_the_plan_checks() -> None:
    assert 10 not in {m.line_number for m in missing_quantity_lines(_TEXT)}


def test_the_card_is_read_by_the_card_line_grammar(
    real_shape_repo: CardRepository,
) -> None:
    text = "Lightning Bolt (M11) 149  #burn  // core\n"
    known = real_shape_repo.get_by_names(["Lightning Bolt"])
    (missing,) = missing_quantity_lines(text)
    assert missing.card_name == "Lightning Bolt"
    assert [w.message for w in missing_quantity_warnings((missing,), known)] == [
        "not a card line: add a quantity (1 Lightning Bolt (M11) 149  #burn  // core)"
    ]

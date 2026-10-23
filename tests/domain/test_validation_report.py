"""validation_report: the one report behind `vimtg validate` and :validate."""

from __future__ import annotations

from vimtg.data.card_repository import CardRepository
from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.validation import validation_report

_MODERN = "// Format: modern\n4 Lightning Bolt\n4 Frobnicator\n52 Mountain\n"
_COMMANDER = "// Format: commander\nCMD: 1 Thrasios, Triton Hero\n1 Rhystic Study\n98 Mountain\n"


def _resolved(text: str, repo: CardRepository) -> dict[str, object]:
    deck = parse_deck_text(text)
    return {n: c for n in deck.unique_card_names() if (c := repo.get_by_name(n)) is not None}


def test_without_a_card_database_legality_is_skipped() -> None:
    report = validation_report(parse_deck_text(_MODERN), None, "modern")
    assert report.legality_checked is False
    assert not [p for p in report.problems if "Card not found" in p.message]
    assert report.bracket == ""


def test_with_a_card_database_unknown_names_are_problems(
    real_shape_repo: CardRepository,
) -> None:
    report = validation_report(
        parse_deck_text(_MODERN), _resolved(_MODERN, real_shape_repo), "modern"
    )
    assert report.legality_checked is True
    assert [p.message for p in report.problems] == ["Card not found: Frobnicator"]


def test_commander_decks_get_a_bracket_estimate(real_shape_repo: CardRepository) -> None:
    report = validation_report(
        parse_deck_text(_COMMANDER), _resolved(_COMMANDER, real_shape_repo), "commander"
    )
    assert report.bracket.startswith("1 Game Changers (Rhystic Study); estimated Commander bracket")


def test_other_formats_get_no_bracket(real_shape_repo: CardRepository) -> None:
    report = validation_report(
        parse_deck_text(_MODERN), _resolved(_MODERN, real_shape_repo), "modern"
    )
    assert report.bracket == ""

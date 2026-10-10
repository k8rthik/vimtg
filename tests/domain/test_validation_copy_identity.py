"""Copy limits count cards, not spellings: 'Fire // Ice' + 'Fire/Ice'
and 'Delver of Secrets' + 'Insectile Aberration' are one card each."""

from __future__ import annotations

from vimtg.data.card_repository import CardRepository
from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.validation import ValidationError, validate_deck


def _validate(text: str, repo: CardRepository | None, fmt: str) -> list[ValidationError]:
    deck = parse_deck_text(text)
    resolved = (
        dict(repo.get_by_names(sorted(deck.unique_card_names()))) if repo else None
    )
    return validate_deck(deck, resolved, fmt, card_db=repo is not None)


def _copy_errors(errs: list[ValidationError]) -> list[str]:
    return [e.message for e in errs if "copies" in e.message]


def test_split_card_spellings_share_one_playset(real_shape_repo: CardRepository) -> None:
    errs = _validate("4 Fire // Ice\n4 Fire/Ice\n52 Mountain\n", real_shape_repo, "modern")
    msgs = _copy_errors(errs)
    assert msgs == [
        "Fire // Ice: 8 copies (max 4 copies in modern)",
        "Fire/Ice: 8 copies (max 4 copies in modern)",
    ]


def test_dfc_face_names_share_one_playset(real_shape_repo: CardRepository) -> None:
    errs = _validate(
        "4 Delver of Secrets\n4 Insectile Aberration\n52 Island\n",
        real_shape_repo,
        "modern",
    )
    assert len(_copy_errors(errs)) == 2
    assert all("8 copies" in m for m in _copy_errors(errs))


def test_commander_singleton_counts_by_card(real_shape_repo: CardRepository) -> None:
    errs = _validate(
        "CMD: 1 Thrasios, Triton Hero\n1 Bonecrusher Giant\n1 Stomp\n97 Island\n",
        real_shape_repo,
        "commander",
    )
    assert any("Stomp: 2 copies (max 1 copy" in m for m in _copy_errors(errs))


def test_without_card_data_separator_spellings_still_meet() -> None:
    errs = _validate("4 Fire // Ice\n4 fire/ice\n52 Mountain\n", None, "")
    assert "More than 4 copies of Fire // Ice" in [e.message for e in errs]


def test_distinct_cards_unaffected(real_shape_repo: CardRepository) -> None:
    errs = _validate(
        "4 Fire // Ice\n4 Lightning Bolt\n52 Mountain\n", real_shape_repo, "modern"
    )
    assert _copy_errors(errs) == []

"""Deck validation rules — the single implementation.

Used by both the CLI (vimtg validate) and the editor (:validate) so the
two can never disagree about what a legal deck looks like.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vimtg.domain.card_types import BASIC_LANDS
from vimtg.domain.deck import Deck, DeckSection

if TYPE_CHECKING:
    from vimtg.domain.card import Card


@dataclass(frozen=True)
class ValidationError:
    level: str  # "error" or "warning"
    message: str
    line_number: int | None = None


def validate_deck(
    deck: Deck,
    resolved: dict[str, Card] | None = None,
) -> list[ValidationError]:
    """Validate deck structure. Returns list of errors/warnings.

    Pass `resolved` (card-name lookups) to also flag unknown names;
    an empty dict means "no card database" and skips that check.
    """
    errors: list[ValidationError] = []

    for entry in deck.entries:
        if entry.quantity <= 0:
            errors.append(
                ValidationError(
                    "error",
                    f"Invalid quantity {entry.quantity} for {entry.card_name}",
                )
            )

    # 4-of rule: copies are counted across mainboard + sideboard
    combined: dict[str, int] = {}
    for entry in deck.entries:
        if entry.section in (DeckSection.MAIN, DeckSection.SIDEBOARD):
            combined[entry.card_name] = (
                combined.get(entry.card_name, 0) + entry.quantity
            )
    for name, qty in combined.items():
        if qty > 4 and name not in BASIC_LANDS:
            errors.append(
                ValidationError("warning", f"More than 4 copies of {name}")
            )

    main_count = sum(e.quantity for e in deck.mainboard())
    if main_count == 0:
        errors.append(ValidationError("error", "No mainboard cards"))
    elif main_count < 60:
        errors.append(
            ValidationError(
                "warning", f"Mainboard has {main_count} cards (minimum 60)"
            )
        )

    side_count = sum(e.quantity for e in deck.sideboard())
    if side_count > 15:
        errors.append(
            ValidationError(
                "warning", f"Sideboard has {side_count} cards (maximum 15)"
            )
        )

    if resolved:
        for entry in deck.entries:
            if entry.card_name not in resolved:
                errors.append(
                    ValidationError(
                        "warning", f"Card not found: {entry.card_name}"
                    )
                )

    return errors

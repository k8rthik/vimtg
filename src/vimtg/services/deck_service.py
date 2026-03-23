"""DeckService — stateless operations on decks: open, save, new, validate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vimtg.data.deck_repository import DeckRepository, parse_deck_text
from vimtg.domain.deck import Deck

if TYPE_CHECKING:
    from vimtg.domain.card import Card


BASIC_LANDS = frozenset({
    "Plains",
    "Island",
    "Swamp",
    "Mountain",
    "Forest",
    "Wastes",
    "Snow-Covered Plains",
    "Snow-Covered Island",
    "Snow-Covered Swamp",
    "Snow-Covered Mountain",
    "Snow-Covered Forest",
})


@dataclass(frozen=True)
class ValidationError:
    level: str  # "error" or "warning"
    message: str
    line_number: int | None = None


class DeckService:
    """Stateless service for deck operations.

    All methods are pure transformations or thin wrappers around the repository.
    No stored state beyond injected dependencies.
    """

    def __init__(
        self,
        deck_repo: DeckRepository,
        card_repo: object | None = None,
    ) -> None:
        self._deck_repo = deck_repo
        self._card_repo = card_repo

    def open_deck(self, path: Path) -> tuple[str, Deck]:
        """Load file and parse into Deck. Returns (raw_text, deck)."""
        text = self._deck_repo.load(path)
        deck = parse_deck_text(text)
        return text, deck

    def save_deck(self, text: str, path: Path) -> None:
        """Save raw deck text to disk."""
        self._deck_repo.save(path, text)

    def new_deck(self, name: str, fmt: str = "", author: str = "") -> str:
        """Create template deck text. Returns the text (not saved to disk)."""
        lines: list[str] = []
        if name:
            lines.append(f"// Deck: {name}")
        if fmt:
            lines.append(f"// Format: {fmt}")
        if author:
            lines.append(f"// Author: {author}")
        lines.append("")
        lines.append("// Mainboard")
        lines.append("")
        lines.append("// Sideboard")
        lines.append("")
        return "\n".join(lines) + "\n"

    def resolve_cards(
        self, deck: Deck
    ) -> tuple[dict[str, Card], list[str]]:
        """Batch lookup card names. Returns (found, unresolved_names)."""
        if self._card_repo is None:
            return {}, list(deck.unique_card_names())
        names = list(deck.unique_card_names())
        found: dict[str, Card] = self._card_repo.get_by_names(names)  # type: ignore[union-attr]
        unresolved = [n for n in names if n not in found]
        return found, unresolved

    def validate(
        self,
        deck: Deck,
        resolved: dict[str, Card] | None = None,
    ) -> list[ValidationError]:
        """Validate deck structure. Returns list of errors/warnings."""
        errors: list[ValidationError] = []

        for entry in deck.entries:
            if entry.quantity <= 0:
                errors.append(
                    ValidationError(
                        "error",
                        f"Invalid quantity {entry.quantity} for {entry.card_name}",
                    )
                )
            if entry.quantity > 4 and entry.card_name not in BASIC_LANDS:
                errors.append(
                    ValidationError(
                        "warning",
                        f"More than 4 copies of {entry.card_name}",
                    )
                )

        main_count = sum(e.quantity for e in deck.mainboard())
        if main_count < 60:
            errors.append(
                ValidationError(
                    "warning",
                    f"Mainboard has {main_count} cards (minimum 60)",
                )
            )

        side_count = sum(e.quantity for e in deck.sideboard())
        if side_count > 15:
            errors.append(
                ValidationError(
                    "warning",
                    f"Sideboard has {side_count} cards (maximum 15)",
                )
            )

        if resolved is not None:
            for entry in deck.entries:
                if entry.card_name not in resolved:
                    errors.append(
                        ValidationError(
                            "warning",
                            f"Card not found: {entry.card_name}",
                        )
                    )

        return errors

"""DeckService — stateless operations on decks: open, save, new, validate."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from vimtg.data.deck_repository import DeckRepository, parse_deck_text
from vimtg.domain.card_types import BASIC_LANDS  # noqa: F401  (re-export)
from vimtg.domain.deck import Deck
from vimtg.domain.validation import ValidationError, validate_deck

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository
    from vimtg.domain.card import Card

__all__ = ["BASIC_LANDS", "DeckService", "ValidationError"]


class DeckService:
    """Stateless service for deck operations.

    All methods are pure transformations or thin wrappers around the repository.
    No stored state beyond injected dependencies.
    """

    def __init__(
        self,
        deck_repo: DeckRepository,
        card_repo: CardRepository | None = None,
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
        found: dict[str, Card] = self._card_repo.get_by_names(names)
        unresolved = [n for n in names if n not in found]
        return found, unresolved

    def validate(
        self,
        deck: Deck,
        resolved: dict[str, Card] | None = None,
    ) -> list[ValidationError]:
        """Validate deck structure. Delegates to domain.validation."""
        return validate_deck(deck, resolved)

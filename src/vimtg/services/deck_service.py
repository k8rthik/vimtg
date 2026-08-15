"""DeckService — stateless operations on decks: open, save, new, validate."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from vimtg.data.deck_repository import DeckRepository, parse_deck_text
from vimtg.domain.card_types import BASIC_LANDS  # noqa: F401  (re-export)
from vimtg.domain.deck import Deck
from vimtg.domain.deck_lines import match_metadata
from vimtg.domain.validation import ValidationError, validate_deck

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository
    from vimtg.domain.card import Card

__all__ = [
    "BASIC_LANDS",
    "DeckService",
    "SCAFFOLD_KEYS",
    "ValidationError",
    "scaffold_missing_metadata",
]

# Metadata lines every deck starts with, editable in-buffer with `i`
SCAFFOLD_KEYS: tuple[str, ...] = ("Deck", "Format", "Tags")


def scaffold_missing_metadata(text: str) -> str:
    """Insert empty '// Key:' lines for scaffold keys absent from the file.

    Missing keys are added after the leading metadata block (line 0 when
    there is none), followed by one blank line when the next line holds
    content. Returns `text` unchanged (same object) when nothing is
    missing, so callers can cheaply detect a no-op.
    """
    lines = text.split("\n")
    present = {
        match[0] for line in lines if (match := match_metadata(line)) is not None
    }
    missing = [key for key in SCAFFOLD_KEYS if key not in present]
    if not missing:
        return text

    insert_at = 0
    while insert_at < len(lines) and match_metadata(lines[insert_at]) is not None:
        insert_at += 1

    scaffold = [f"// {key}:" for key in missing]
    if insert_at < len(lines) and lines[insert_at].strip():
        scaffold.append("")
    new_lines = lines[:insert_at] + scaffold + lines[insert_at:]
    return "\n".join(new_lines)


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
        lines.append(f"// Deck: {name}".rstrip())
        lines.append(f"// Format: {fmt}".rstrip())
        if author:
            lines.append(f"// Author: {author}")
        lines.append("// Tags:")
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

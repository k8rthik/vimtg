"""DeckService — stateless operations on decks: open, save, new, validate."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
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
    "Scaffold",
    "ValidationError",
    "scaffold_metadata",
    "editor_line_numbers",
    "editor_view_text",
    "scaffold_missing_metadata",
    "strip_unused_scaffold",
]

# Metadata lines every deck starts with, editable in-buffer with `i`
SCAFFOLD_KEYS: tuple[str, ...] = ("Deck", "Format", "Tags")


@dataclass(frozen=True)
class Scaffold:
    """What scaffolding added to a deck's text, so a save can take the
    unused part back out: the metadata keys inserted and whether the
    blank line after them is scaffolding too (not the file's own)."""

    keys: frozenset[str] = frozenset()
    blank: bool = False


NO_SCAFFOLD = Scaffold()


def scaffold_metadata(text: str) -> tuple[str, Scaffold]:
    """Insert empty '// Key:' lines for scaffold keys absent from the file.

    Missing keys are added after the leading metadata block (line 0 when
    there is none), followed by one blank line when the next line holds
    content. Returns `text` unchanged (same object) when nothing is
    missing, so callers can cheaply detect a no-op; the Scaffold records
    what was added for strip_unused_scaffold.
    """
    lines = text.split("\n")
    present = {
        match[0] for line in lines if (match := match_metadata(line)) is not None
    }
    missing = [key for key in SCAFFOLD_KEYS if key not in present]
    if not missing:
        return text, NO_SCAFFOLD

    insert_at = 0
    while insert_at < len(lines) and match_metadata(lines[insert_at]) is not None:
        insert_at += 1

    scaffold = [f"// {key}:" for key in missing]
    blank = insert_at < len(lines) and bool(lines[insert_at].strip())
    if blank:
        scaffold.append("")
    # An empty deck gets its blank later, ahead of scaffold_deck_body's DCK:
    blank = blank or not text.strip()
    new_lines = lines[:insert_at] + scaffold + lines[insert_at:]
    return "\n".join(new_lines), Scaffold(frozenset(missing), blank)


def scaffold_missing_metadata(text: str) -> str:
    """scaffold_metadata without the record of what was added."""
    return scaffold_metadata(text)[0]


def strip_unused_scaffold(text: str, added: Scaffold) -> str:
    """Drop scaffold lines that are still empty before writing to disk.

    The editor shows '// Deck:' / '// Format:' / '// Tags:' so they can
    be filled in place, but a file that never had them should not gain
    empty lines (git-diff noise) just by being saved. Only keys the
    scaffold added are touched, so metadata the file already had —
    empty or not — round-trips unchanged.
    """
    if not added.keys:
        return text
    lines = text.split("\n")
    end = 0
    while end < len(lines) and match_metadata(lines[end]) is not None:
        end += 1
    kept: list[str] = []
    for line in lines[:end]:
        meta = match_metadata(line)
        if meta is not None and meta[0] in added.keys and not meta[1]:
            continue
        kept.append(line)
    if len(kept) == end:
        return text
    rest = lines[end:]
    # The separating blank the scaffold added goes with the last of its lines
    scaffold_left = any(
        (meta := match_metadata(line)) is not None and meta[0] in added.keys
        for line in kept
    )
    if added.blank and not scaffold_left and rest and not rest[0].strip():
        rest = rest[1:]
    return "\n".join(kept + rest)


def scaffold_deck_body(text: str) -> str:
    """Give a deck with no cards its zone structure: a 'DCK:' block, and
    a 'CMD:' block first when the deck declares the commander format.

    Decks that already have any cards or zone headers are returned
    unchanged (same object) — existing files are never restructured.
    """
    from vimtg.domain.deck_lines import parse_zone_header

    lines = text.split("\n")
    if any(parse_zone_header(line) is not None for line in lines):
        return text
    deck = parse_deck_text(text)
    if deck.entries:
        return text

    blocks: list[str] = []
    if deck.metadata.format.strip().lower() in ("commander", "brawl"):
        blocks.extend(["CMD:", ""])
    blocks.append("DCK:")

    out = text.rstrip("\n")
    if out:
        return out + "\n\n" + "\n".join(blocks) + "\n"
    return "\n".join(blocks) + "\n"


def needs_new_deck_prompt(text: str) -> bool:
    """True for a deck still waiting to be set up: no cards yet and a
    blank '// Deck:' name or '// Format:'."""
    deck = parse_deck_text(text)
    if deck.entries:
        return False
    return not deck.metadata.name.strip() or not deck.metadata.format.strip()


def set_deck_identity(text: str, name: str, fmt: str) -> str:
    """Fill the '// Deck:' and '// Format:' lines of a new deck.

    Blank answers leave their line alone. Lines missing from the text
    are added to the leading metadata block. A commander/brawl format
    on a deck with no CMD: block gains one ahead of DCK:, as `vimtg new
    --format commander` would have written.
    """
    from vimtg.domain.deck_lines import parse_zone_header

    lines = text.split("\n")
    for key, value in (("Deck", name.strip()), ("Format", fmt.strip())):
        if not value:
            continue
        row = next(
            (
                i for i, line in enumerate(lines)
                if (m := match_metadata(line)) is not None and m[0].lower() == key.lower()
            ),
            None,
        )
        if row is not None:
            lines[row] = f"// {key}: {value}"
            continue
        end = 0
        while end < len(lines) and match_metadata(lines[end]) is not None:
            end += 1
        lines.insert(end, f"// {key}: {value}")
    if fmt.strip().lower() in ("commander", "brawl"):
        headers = [parse_zone_header(line) for line in lines]
        if "CMD" not in headers and "DCK" in headers:
            dck = headers.index("DCK")
            lines[dck:dck] = ["CMD:", ""]
    return "\n".join(lines)


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
        # Only metadata with content is written; the editor scaffolds
        # the empty keys back in for display when the file is opened
        lines: list[str] = [f"// Deck: {name}".rstrip()]
        if fmt.strip():
            lines.append(f"// Format: {fmt.strip()}")
        if author:
            lines.append(f"// Author: {author}")
        lines.append("")
        if fmt.strip().lower() in ("commander", "brawl"):
            lines.append("CMD:")
            lines.append("")
        lines.append("DCK:")
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
        fmt: str = "",
        *,
        card_db: bool | None = None,
    ) -> list[ValidationError]:
        """Validate deck structure and format legality. Delegates to domain."""
        return validate_deck(deck, resolved, fmt, card_db=card_db)


def editor_view_text(raw: str) -> str:
    """The deck text exactly as the editor shows a file with `raw` text:
    scaffold metadata and zone blocks filled in, sections normalized."""
    from vimtg.editor.buffer import Buffer
    from vimtg.editor.sections import normalize_sections

    text = scaffold_deck_body(scaffold_metadata(raw)[0])
    return normalize_sections(Buffer.from_text(text)).to_text()


def editor_line_numbers(raw: str) -> dict[int, int]:
    """File line -> the line the editor shows it on (both 1-based), for
    every line the editor keeps unchanged. Opening a deck can add lines
    (empty '// Tags:' scaffolding, a blank before a header), so a file's
    line 2 may be the editor's line 5; `vimtg validate` reports both."""
    file_lines = raw.split("\n")
    shown = editor_view_text(raw).split("\n")
    matcher = difflib.SequenceMatcher(a=file_lines, b=shown, autojunk=False)
    mapping: dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            mapping[block.a + k + 1] = block.b + k + 1
    return mapping

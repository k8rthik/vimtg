"""Deck file parser, serializer, and filesystem repository."""

from __future__ import annotations

import re
from pathlib import Path

from vimtg.domain.deck import (
    CommentLine,
    Deck,
    DeckEntry,
    DeckMetadata,
    DeckSection,
)

_METADATA_PATTERN = re.compile(r"^//\s*(Deck|Format|Author|Description):\s*(.+)$")
_SIDEBOARD_PATTERN = re.compile(r"^SB:\s*(\d+)\s+(.+)$")
_COMMANDER_PATTERN = re.compile(r"^CMD:\s*(\d+)\s+(.+)$")
_MAINBOARD_PATTERN = re.compile(r"^(\d+)\s+(.+)$")


def _parse_metadata_block(lines: tuple[str, ...]) -> DeckMetadata:
    """Extract metadata from // Key: Value comment lines."""
    name = ""
    fmt = ""
    author = ""
    description = ""
    for line in lines:
        match = _METADATA_PATTERN.match(line)
        if match:
            key = match.group(1).lower()
            value = match.group(2).strip()
            if key == "deck":
                name = value
            elif key == "format":
                fmt = value
            elif key == "author":
                author = value
            elif key == "description":
                description = value
    return DeckMetadata(
        name=name, format=fmt, author=author, description=description
    )


def parse_deck_text(text: str) -> Deck:
    """Parse deck text into a Deck domain object.

    Rules:
    - Lines starting with // are comments; first block with
      // Key: Value becomes metadata.
    - SB: N CardName -> sideboard entry.
    - CMD: N CardName -> commander entry.
    - N CardName -> mainboard entry.
    - Blank/invalid lines are skipped gracefully.
    """
    raw_lines = text.split("\n") if text else []

    entries: list[DeckEntry] = []
    comments: list[CommentLine] = []
    metadata_lines: list[str] = []

    for line_number, raw_line in enumerate(raw_lines, start=1):
        line = raw_line.strip()

        if not line:
            continue

        # Comment lines start with //
        if line.startswith("//"):
            if _METADATA_PATTERN.match(line):
                metadata_lines.append(line)
            else:
                comments.append(
                    CommentLine(line_number=line_number, text=line)
                )
            continue

        # Sideboard entry
        sb_match = _SIDEBOARD_PATTERN.match(line)
        if sb_match:
            entries.append(
                DeckEntry(
                    quantity=int(sb_match.group(1)),
                    card_name=sb_match.group(2).strip(),
                    section=DeckSection.SIDEBOARD,
                )
            )
            continue

        # Commander entry
        cmd_match = _COMMANDER_PATTERN.match(line)
        if cmd_match:
            entries.append(
                DeckEntry(
                    quantity=int(cmd_match.group(1)),
                    card_name=cmd_match.group(2).strip(),
                    section=DeckSection.COMMANDER,
                )
            )
            continue

        # Mainboard entry
        main_match = _MAINBOARD_PATTERN.match(line)
        if main_match:
            entries.append(
                DeckEntry(
                    quantity=int(main_match.group(1)),
                    card_name=main_match.group(2).strip(),
                    section=DeckSection.MAIN,
                )
            )
            continue

        # Invalid line — skip gracefully

    metadata = _parse_metadata_block(tuple(metadata_lines))

    return Deck(
        metadata=metadata,
        entries=tuple(entries),
        comments=tuple(comments),
    )


def serialize_deck(deck: Deck) -> str:
    """Serialize a Deck back to text format.

    - Metadata as // Key: Value comments.
    - Mainboard entries grouped first.
    - Sideboard entries with SB: prefix.
    - Commander entries with CMD: prefix.
    """
    lines: list[str] = []

    # Metadata
    if deck.metadata.name:
        lines.append(f"// Deck: {deck.metadata.name}")
    if deck.metadata.format:
        lines.append(f"// Format: {deck.metadata.format}")
    if deck.metadata.author:
        lines.append(f"// Author: {deck.metadata.author}")
    if deck.metadata.description:
        lines.append(f"// Description: {deck.metadata.description}")

    # Group entries by section
    sections_order = (
        DeckSection.COMMANDER,
        DeckSection.COMPANION,
        DeckSection.MAIN,
        DeckSection.SIDEBOARD,
    )

    for section in sections_order:
        section_entries = tuple(
            e for e in deck.entries if e.section == section
        )
        if not section_entries:
            continue

        if lines:
            lines.append("")

        for entry in section_entries:
            if section == DeckSection.SIDEBOARD:
                lines.append(f"SB: {entry.quantity} {entry.card_name}")
            elif section == DeckSection.COMMANDER:
                lines.append(f"CMD: {entry.quantity} {entry.card_name}")
            else:
                lines.append(f"{entry.quantity} {entry.card_name}")

    if lines:
        lines.append("")

    return "\n".join(lines)


class DeckRepository:
    """Filesystem operations for .deck files."""

    def load(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def save(self, path: Path, text: str) -> None:
        """Atomic write: write to temp file, then rename."""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.rename(path)

    def list_decks(self, directory: Path) -> list[Path]:
        return sorted(directory.glob("*.deck"))

    def exists(self, path: Path) -> bool:
        return path.is_file()

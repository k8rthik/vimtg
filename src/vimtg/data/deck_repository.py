"""Deck file parser, serializer, and filesystem repository."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from vimtg.domain.deck import (
    CommentLine,
    Deck,
    DeckEntry,
    DeckMetadata,
    DeckSection,
)
from vimtg.domain.deck_lines import (
    CARD_PATTERN as _MAINBOARD_PATTERN,
)
from vimtg.domain.deck_lines import (
    CMD_PATTERN as _COMMANDER_PATTERN,
)
from vimtg.domain.deck_lines import (
    METADATA_PATTERN as _METADATA_PATTERN,
)
from vimtg.domain.deck_lines import (
    SB_PATTERN as _SIDEBOARD_PATTERN,
)
from vimtg.domain.deck_lines import (
    clamp_quantity,
)
from vimtg.domain.tags import format_inline_tags, parse_inline_tags, strip_inline_tags


def _parse_metadata_block(lines: tuple[str, ...]) -> DeckMetadata:
    """Extract metadata from // Key: Value comment lines."""
    name = ""
    fmt = ""
    author = ""
    description = ""
    tags: frozenset[str] = frozenset()
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
            elif key == "tags":
                tags = frozenset(
                    t.strip().lower() for t in value.split(",") if t.strip()
                )
    return DeckMetadata(
        name=name, format=fmt, author=author, description=description,
        tags=tags,
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
            raw_name = sb_match.group(2).strip()
            card_tags = parse_inline_tags(raw_name)
            entries.append(
                DeckEntry(
                    quantity=clamp_quantity(int(sb_match.group(1))),
                    card_name=strip_inline_tags(raw_name).strip(),
                    section=DeckSection.SIDEBOARD,
                    tags=card_tags,
                )
            )
            continue

        # Commander entry
        cmd_match = _COMMANDER_PATTERN.match(line)
        if cmd_match:
            raw_name = cmd_match.group(2).strip()
            card_tags = parse_inline_tags(raw_name)
            entries.append(
                DeckEntry(
                    quantity=clamp_quantity(int(cmd_match.group(1))),
                    card_name=strip_inline_tags(raw_name).strip(),
                    section=DeckSection.COMMANDER,
                    tags=card_tags,
                )
            )
            continue

        # Mainboard entry
        main_match = _MAINBOARD_PATTERN.match(line)
        if main_match:
            raw_name = main_match.group(2).strip()
            card_tags = parse_inline_tags(raw_name)
            entries.append(
                DeckEntry(
                    quantity=clamp_quantity(int(main_match.group(1))),
                    card_name=strip_inline_tags(raw_name).strip(),
                    section=DeckSection.MAIN,
                    tags=card_tags,
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
    if deck.metadata.tags:
        lines.append(f"// Tags: {', '.join(sorted(deck.metadata.tags))}")

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
            tag_suffix = format_inline_tags(entry.tags)
            if section == DeckSection.SIDEBOARD:
                lines.append(f"SB: {entry.quantity} {entry.card_name}{tag_suffix}")
            elif section == DeckSection.COMMANDER:
                lines.append(f"CMD: {entry.quantity} {entry.card_name}{tag_suffix}")
            else:
                lines.append(f"{entry.quantity} {entry.card_name}{tag_suffix}")

    if lines:
        lines.append("")

    return "\n".join(lines)


class DeckRepository:
    """Filesystem operations for .deck files."""

    def load(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def save(self, path: Path, text: str) -> None:
        """Atomic write: stage to a unique temp file, then replace.

        mkstemp avoids two instances racing on the same predictable
        temp name (burn.deck and burn.tmp colliding, etc.).
        """
        fd, tmp_path = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def list_decks(self, directory: Path, by_mtime: bool = False) -> list[Path]:
        """List .deck files, sorted by name (default) or newest first."""
        decks = list(directory.glob("*.deck"))
        if by_mtime:

            def _mtime(p: Path) -> float:
                try:
                    return p.stat().st_mtime
                except OSError:  # deleted between glob and stat
                    return 0.0

            return sorted(decks, key=_mtime, reverse=True)
        return sorted(decks, key=lambda p: p.name.lower())

    def exists(self, path: Path) -> bool:
        return path.is_file()

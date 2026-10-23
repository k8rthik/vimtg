"""Deck file parser, serializer, and filesystem repository."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from vimtg.data.file_io import atomic_write_text
from vimtg.domain.categories import format_inline_category
from vimtg.domain.deck import (
    CommentLine,
    Deck,
    DeckEntry,
    DeckMetadata,
    DeckSection,
)
from vimtg.domain.deck_lines import (
    METADATA_PATTERN as _METADATA_PATTERN,
)
from vimtg.domain.deck_lines import (
    PLAN_TAG,
    MissingQuantityLine,
    format_inline_comment,
    is_mtgo_sideboard_header,
    parse_card_line,
    parse_missing_quantity_line,
    parse_plan_header_parts,
    parse_plan_line,
    parse_zone_header,
    strip_bom,
    zone_block_contexts,
)
from vimtg.domain.sideboard_plan import PlanEntry, SideboardPlan
from vimtg.domain.tags import format_inline_tags


def _parse_metadata_block(lines: tuple[str, ...]) -> DeckMetadata:
    """Extract metadata from // Key: Value comment lines."""
    name = ""
    fmt = ""
    author = ""
    description = ""
    source = ""
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
            elif key == "source":
                source = value
            elif key == "tags":
                tags = frozenset(
                    t.strip().lower() for t in value.split(",") if t.strip()
                )
    return DeckMetadata(
        name=name, format=fmt, author=author, description=description,
        source=source, tags=tags,
    )


# Zone tag (a line's own prefix, or the block header its indented bare
# card lines sit under) → the deck section
_ZONE_SECTIONS = {
    "DCK": DeckSection.MAIN,
    "CMD": DeckSection.COMMANDER,
    "CMP": DeckSection.COMPANION,
    "SB": DeckSection.SIDEBOARD,
    "MB": DeckSection.MAYBEBOARD,
}


def _parse_entry_line(line: str, line_number: int) -> DeckEntry | None:
    """Parse one SB:/CMD:/mainboard card line, or None if not a card line."""
    card = parse_card_line(line)
    if card is None:
        return None
    return DeckEntry(
        quantity=card.quantity,
        card_name=card.name,
        section=_ZONE_SECTIONS[card.zone],
        category=card.category,
        tags=card.tags,
        comment=card.comment,
        line_number=line_number,
    )


def missing_quantity_lines(text: str) -> tuple[MissingQuantityLine, ...]:
    """Lines the parser skips that could name a card ('Lightning Bolt',
    '4x Shock'); lines in a sideboard plan are left to the plan checks."""
    contexts = zone_block_contexts(strip_bom(text).split("\n"))
    found: list[MissingQuantityLine] = []

    def on_skip(line_number: int, line: str) -> None:
        missing = parse_missing_quantity_line(line_number, line)
        if missing is not None and contexts[line_number - 1] != PLAN_TAG:
            found.append(missing)

    parse_deck_text(text, on_skip=on_skip)
    return tuple(found)


def parse_deck_text(
    text: str, on_skip: Callable[[int, str], None] | None = None
) -> Deck:
    """Parse deck text into a Deck domain object.

    Rules:
    - Lines starting with // are comments; first block with
      // Key: Value becomes metadata.
    - SB: N CardName -> sideboard entry.
    - CMD: N CardName -> commander entry.
    - CMP: N CardName -> companion entry.
    - N CardName -> mainboard entry.
    - A bare 'DCK:'/'CMD:'/... line opens a Python-style zone block:
      bare card lines indented beneath it belong to that zone
      (explicit prefixes always win).
    - A bare 'Sideboard' line (MTGO/Arena style) makes the unprefixed
      card lines after it sideboard cards (deck_lines.zone_block_contexts
      models both kinds of block, so the editor buffer agrees).
    - Pasted '(SET) 123' / '*F*' printing suffixes are stripped from
      card names; a leading UTF-8 BOM is ignored.
    - Blank/invalid lines are skipped gracefully; `on_skip(line_number,
      line)` is told about each invalid one.
    """
    text = strip_bom(text)
    raw_lines = text.split("\n") if text else []
    block_contexts = zone_block_contexts(raw_lines)

    entries: list[DeckEntry] = []
    comments: list[CommentLine] = []
    metadata_lines: list[str] = []
    plans: list[SideboardPlan] = []

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

        # Bare zone block headers are structural, like section headers
        if parse_zone_header(line) is not None or is_mtgo_sideboard_header(line):
            continue

        # 'VS: name' opens a sideboard plan; its indented lines follow
        header = parse_plan_header_parts(line)
        if header is not None:
            plans.append(SideboardPlan(
                name=header[0], note=header[1], line_number=line_number,
            ))
            continue

        block = block_contexts[line_number - 1]
        if block == PLAN_TAG:
            plan_entry = _parse_plan_entry_line(line, line_number)
            if plan_entry is not None and plans:
                plans[-1] = replace(
                    plans[-1], entries=plans[-1].entries + (plan_entry,)
                )
                continue
            # An explicitly prefixed zone line inside a plan block is
            # still a zone card (explicit prefix wins) — fall through

        entry = _parse_entry_line(line, line_number)
        if entry is not None:
            if entry.section == DeckSection.MAIN and block is not None:
                if block == PLAN_TAG:
                    continue  # unsigned line handled above; never a card
                entry = replace(entry, section=_ZONE_SECTIONS[block])
            entries.append(entry)
        elif on_skip is not None:
            # Invalid line — skipped gracefully, but reported when asked
            on_skip(line_number, line)

    metadata = _parse_metadata_block(tuple(metadata_lines))

    return Deck(
        metadata=metadata,
        entries=tuple(entries),
        comments=tuple(comments),
        plans=tuple(plans),
    )


def _parse_plan_entry_line(line: str, line_number: int) -> PlanEntry | None:
    """Parse one '[+-]N Card  // note' plan line, or None.

    Explicitly prefixed zone lines ('SB: 1 X') and lines naming no card
    ('-1 #tag') are not plan entries (see deck_lines.parse_plan_line).
    """
    plan = parse_plan_line(line)
    if plan is None:
        return None
    return PlanEntry(
        card_name=plan.name,
        quantity=plan.quantity,
        sign=plan.sign,
        comment=plan.comment,
        line_number=line_number,
    )


def serialize_deck(deck: Deck) -> str:
    """Serialize a Deck back to text format.

    - Metadata as // Key: Value comments.
    - Mainboard entries grouped first.
    - Sideboard entries with SB: prefix.
    - Commander entries with CMD: prefix.
    - Companion entry with CMP: prefix.
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
    if deck.metadata.source:
        lines.append(f"// Source: {deck.metadata.source}")
    if deck.metadata.tags:
        lines.append(f"// Tags: {', '.join(sorted(deck.metadata.tags))}")

    # Freeform comments (positions are not reconstructed, but the text
    # must survive — :import and VCS cherry-pick serialize through here)
    for comment in sorted(deck.comments, key=lambda c: c.line_number):
        lines.append(comment.text)

    # Group entries by section
    sections_order = (
        DeckSection.COMMANDER,
        DeckSection.COMPANION,
        DeckSection.MAIN,
        DeckSection.SIDEBOARD,
        DeckSection.MAYBEBOARD,
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
            suffix = (
                format_inline_category(entry.category)
                + format_inline_tags(entry.tags)
                + format_inline_comment(entry.comment)
            )
            if section == DeckSection.SIDEBOARD:
                lines.append(f"SB: {entry.quantity} {entry.card_name}{suffix}")
            elif section == DeckSection.MAYBEBOARD:
                lines.append(f"MB: {entry.quantity} {entry.card_name}{suffix}")
            elif section == DeckSection.COMMANDER:
                lines.append(f"CMD: {entry.quantity} {entry.card_name}{suffix}")
            elif section == DeckSection.COMPANION:
                lines.append(f"CMP: {entry.quantity} {entry.card_name}{suffix}")
            else:
                lines.append(f"{entry.quantity} {entry.card_name}{suffix}")

    # Sideboard plans come last, always in block style
    for plan in deck.plans:
        if lines:
            lines.append("")
        lines.append(f"VS: {plan.name}{format_inline_comment(plan.note)}")
        for plan_entry in plan.entries:
            lines.append(f"    {plan_entry.text()}")

    if lines:
        lines.append("")

    return "\n".join(lines)


class DeckRepository:
    """Filesystem operations for .deck files."""

    def load(self, path: Path) -> str:
        # utf-8-sig drops a BOM that Windows editors prepend
        return path.read_text(encoding="utf-8-sig")

    def save(self, path: Path, text: str) -> None:
        """Atomic write that keeps symlinks and permissions (see file_io)."""
        atomic_write_text(path, text)

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

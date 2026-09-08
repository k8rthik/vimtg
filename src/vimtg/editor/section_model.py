"""Parsed section model — one definition of what a section covers.

A header line owns every line down to the next header (section or
plan). Within that extent the section's cards are the lines of ITS
zone: a '// Creatures' header groups mainboard cards, '// Sideboard'
groups sideboard lines, and a type header indented inside an 'SB:'
block groups that block's zone. Insertion, header counts, empty-section
cleanup, and category lookup all read this model, so they can never
disagree about where a section starts, ends, or what it holds.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from vimtg.domain.deck_lines import PLAN_TAG, zone_context_at
from vimtg.domain.section_keys import (
    SectionKey,
    SectionKind,
    parse_section_key,
)
from vimtg.editor.buffer import ZONE_TAG_TYPES, Buffer, LineType

_HEADER_TYPES = (LineType.SECTION_HEADER, LineType.PLAN_HEADER)


@dataclass(frozen=True)
class Section:
    key: SectionKey
    header_row: int
    end: int  # exclusive — the next header row, or the line count
    zone: LineType
    card_rows: tuple[int, ...]
    indent: str

    @property
    def start(self) -> int:
        return self.header_row + 1

    @property
    def is_empty(self) -> bool:
        return not self.card_rows

    @property
    def is_structural(self) -> bool:
        return self.key.is_structural

    @property
    def insert_row(self) -> int:
        """Where a new card of this section belongs: after its last card,
        or directly under the header when it has none."""
        return self.card_rows[-1] + 1 if self.card_rows else self.start

    def contains(self, row: int) -> bool:
        return self.header_row <= row < self.end


def _header_zone(texts: Sequence[str], row: int, key: SectionKey) -> LineType:
    """The LineType of the cards a header groups."""
    if key.kind in (SectionKind.ZONE_LABEL, SectionKind.ZONE_BLOCK):
        return ZONE_TAG_TYPES[key.zone_tag]
    ctx = zone_context_at(texts, row)
    if ctx == PLAN_TAG:
        return LineType.PLAN_ENTRY
    if ctx is not None:
        return ZONE_TAG_TYPES[ctx]
    return ZONE_TAG_TYPES[key.zone_tag]


def parse_sections(buf: Buffer) -> tuple[Section, ...]:
    """Every section header in the buffer with its extent and cards."""
    lines = buf.get_lines()
    texts = [bl.text for bl in lines]
    header_rows = [
        i for i, bl in enumerate(lines) if bl.line_type in _HEADER_TYPES
    ]
    sections: list[Section] = []
    for idx, row in enumerate(header_rows):
        key = parse_section_key(texts[row])
        if key is None:
            continue  # a plan header — bounds sections but is not one
        end = header_rows[idx + 1] if idx + 1 < len(header_rows) else len(lines)
        zone = _header_zone(texts, row, key)
        card_rows = tuple(
            i for i in range(row + 1, end) if lines[i].line_type == zone
        )
        text = texts[row]
        indent = text[: len(text) - len(text.lstrip())]
        sections.append(Section(key, row, end, zone, card_rows, indent))
    return tuple(sections)


def section_at(sections: Sequence[Section], row: int) -> Section | None:
    """The section whose header or body holds `row`, else None."""
    for section in sections:
        if section.contains(row):
            return section
    return None


def find_section(
    sections: Sequence[Section], key: SectionKey, zone: LineType | None = None
) -> Section | None:
    """First section with `key` (and `zone`, when given), else None."""
    for section in sections:
        if section.key == key and (zone is None or section.zone == zone):
            return section
    return None

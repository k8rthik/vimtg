"""Render-time card totals for header lines in a deck buffer.

Maps header line indices to the card quantities they cover so the TUI
can annotate them ('// Creatures (12)', 'DCK: (60)', '// Deck: X ·
60/15 cards'). Purely visual — nothing here is ever written into the
file.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from typing import NamedTuple

from vimtg.domain.deck_lines import match_metadata, parse_zone_header
from vimtg.editor.buffer import (
    CARD_LINE_TYPES,
    ZONE_TAG_TYPES,
    Buffer,
    LineType,
)
from vimtg.editor.plan_ops import plan_blocks, plan_totals
from vimtg.editor.section_model import parse_sections

# The zones that make up "the deck" for the '// Deck:' title total —
# mainboard plus command-zone cards, excluding side/maybeboard.
_DECK_ZONES = (
    LineType.CARD_ENTRY,
    LineType.COMMANDER_ENTRY,
    LineType.COMPANION_ENTRY,
)


class HeaderCount(NamedTuple):
    """Card total for one header line. `side` is nonzero only on the
    '// Deck:' title line, where it carries the sideboard total so the
    TUI can render the main/side split ('60/15 cards'). A 'VS:' plan
    header sets `plan` and carries its boarding totals in `outs`/`ins`
    instead ('(-4 +4)')."""

    main: int
    side: int = 0
    outs: int = 0
    ins: int = 0
    plan: bool = False

    @property
    def unbalanced(self) -> bool:
        return self.plan and self.outs != self.ins


def _zone_totals(buf: Buffer) -> dict[LineType, int]:
    """Total card quantity per zone across the whole buffer."""
    totals: dict[LineType, int] = dict.fromkeys(CARD_LINE_TYPES, 0)
    for i in range(buf.line_count()):
        line_type = buf.get_line(i).line_type
        if line_type in CARD_LINE_TYPES:
            totals[line_type] += buf.quantity_at(i) or 0
    return totals


def _section_totals(buf: Buffer) -> dict[int, int]:
    """Quantity under each '// Creatures'-style header, keyed by row:
    the section's own cards per the shared section model, so the count
    agrees with what insertion and cleanup consider the section."""
    return {
        section.header_row: sum(
            buf.quantity_at(row) or 0 for row in section.card_rows
        )
        for section in parse_sections(buf)
        if not section.is_structural
    }


def header_counts(buf: Buffer) -> dict[int, HeaderCount]:
    """Card totals keyed by header line index. Zero totals are omitted.

    - Zone block headers ('DCK:', 'SB:', ...) carry their zone's total
      across the whole buffer — DCK: is the deck total.
    - Type/category/label headers ('// Creatures', '// @ramp',
      '// Sideboard') carry the quantity of their own cards.
    - The '// Deck:' metadata line carries the deck total (mainboard
      plus commander and companion) with the sideboard total in `side`;
      maybeboard cards count toward neither.
    - 'VS:' plan headers carry their -outs/+ins totals (always present,
      an empty plan reads '(-0 +0)').
    """
    totals = _zone_totals(buf)
    section_totals = _section_totals(buf)
    counts: dict[int, HeaderCount] = {}
    for block in plan_blocks(buf):
        outs, ins = plan_totals(buf, block)
        counts[block.header_row] = HeaderCount(0, outs=outs, ins=ins, plan=True)
    for i in range(buf.line_count()):
        bl = buf.get_line(i)
        if bl.line_type == LineType.METADATA:
            meta = match_metadata(bl.text)
            if meta is not None and meta[0] == "Deck":
                count = HeaderCount(
                    main=sum(totals[zone] for zone in _DECK_ZONES),
                    side=totals[LineType.SIDEBOARD_ENTRY],
                )
            else:
                continue
        elif bl.line_type == LineType.SECTION_HEADER:
            tag = parse_zone_header(bl.text)
            count = HeaderCount(
                totals[ZONE_TAG_TYPES[tag]]
                if tag is not None
                else section_totals.get(i, 0)
            )
        else:
            continue
        if count.main or count.side:
            counts[i] = count
    return counts

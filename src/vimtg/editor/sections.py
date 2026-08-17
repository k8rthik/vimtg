"""Section normalization for deck buffers.

Removes section headers with no cards, collapses runs of blank lines,
and keeps one blank line before each header. Pure buffer-to-buffer
logic; returns the input Buffer unchanged (same object) when the text
is already normalized, so callers can detect "no change" by identity.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from vimtg.domain.deck_lines import parse_zone_header
from vimtg.editor.buffer import (
    Buffer,
    LineType,
    classify_line,
)

# Text section headers whose cards live in a non-main zone; every other
# header ("// Creatures", "// @ramp", ...) labels mainboard cards.
_LABEL_ZONE_TYPES: dict[str, LineType] = {
    "Sideboard": LineType.SIDEBOARD_ENTRY,
    "Maybeboard": LineType.MAYBEBOARD_ENTRY,
    "Commander": LineType.COMMANDER_ENTRY,
    "Companion": LineType.COMPANION_ENTRY,
}


def _expected_card_type(header_text: str) -> LineType | None:
    """The card LineType a header's section is made of.

    None for bare zone block headers ('DCK:', 'CMD:', ...) — those are
    structural zone declarations, not derived groupings, and are never
    auto-dropped.
    """
    if parse_zone_header(header_text) is not None:
        return None
    label = header_text.strip().removeprefix("//").strip()
    return _LABEL_ZONE_TYPES.get(label, LineType.CARD_ENTRY)


def normalize_sections(buffer: Buffer) -> Buffer:
    """Return a normalized Buffer, or `buffer` itself if already clean."""
    lines = [
        (buffer.get_line(i).text, buffer.get_line(i).line_type)
        for i in range(buffer.line_count())
    ]

    kept = _drop_empty_headers(lines)
    collapsed = _collapse_blank_runs(kept)
    padded = _pad_before_headers(collapsed)

    if [text for text, _ in lines] == padded:
        return buffer
    return Buffer.from_text("\n".join(padded) + "\n")


def _drop_empty_headers(
    lines: list[tuple[str, LineType]],
) -> list[tuple[str, LineType]]:
    """Drop section headers with no card lines before the next section.

    Zone-aware: a '// Creature' header is only occupied by mainboard
    cards — a CMD:/SB: line sitting where the section's cards used to
    be does not keep it alive.
    """
    to_delete: set[int] = set()
    for i, (text, line_type) in enumerate(lines):
        if line_type != LineType.SECTION_HEADER:
            continue
        expected = _expected_card_type(text)
        if expected is None:
            continue  # bare zone block header — structural, keep
        has_cards = False
        for _, next_type in lines[i + 1:]:
            if next_type == LineType.BLANK:
                continue
            if next_type == expected:
                has_cards = True
            break
        if not has_cards:
            to_delete.add(i)
            if i + 1 < len(lines) and lines[i + 1][1] == LineType.BLANK:
                to_delete.add(i + 1)
    return [entry for i, entry in enumerate(lines) if i not in to_delete]


def _collapse_blank_runs(
    lines: list[tuple[str, LineType]],
) -> list[tuple[str, LineType]]:
    """Keep at most one blank line in any run of blanks."""
    collapsed: list[tuple[str, LineType]] = []
    prev_blank = False
    for text, line_type in lines:
        is_blank = line_type == LineType.BLANK
        if is_blank and prev_blank:
            continue
        collapsed.append((text, line_type))
        prev_blank = is_blank
    return collapsed


def _pad_before_headers(lines: list[tuple[str, LineType]]) -> list[str]:
    """Insert a blank line before each section header where missing."""
    padded: list[str] = []
    for text, line_type in lines:
        if line_type == LineType.SECTION_HEADER and padded:
            prev_type = classify_line(padded[-1])
            if prev_type not in (LineType.BLANK, LineType.METADATA):
                padded.append("")
        padded.append(text)
    return padded

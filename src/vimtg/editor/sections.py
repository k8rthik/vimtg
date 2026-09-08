"""Section placement and normalization for deck buffers.

Built on the parsed section model (vimtg.editor.section_model): a
section's identity is its SectionKey and its extent runs to the next
header, so the insert row, the empty-section cleanup, and the duplicate
merge below all agree with header counts and category lookup.

Normalization merges duplicate sections, removes headers with no cards,
collapses runs of blank lines, and keeps one blank line before each
header. Pure buffer-to-buffer logic; returns the input Buffer unchanged
(same object) when the text is already normalized, so callers can
detect "no change" by identity.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from vimtg.domain.categories import UNCATEGORIZED_LABEL
from vimtg.domain.deck_lines import (
    CARD_PATTERN,
    block_header_tag,
    parse_zone_header,
    zone_context_effect,
    zone_running_context,
)
from vimtg.domain.section_keys import (
    SectionKey,
    SectionKind,
    section_key_for_label,
)
from vimtg.editor.buffer import Buffer, LineType, classify_line
from vimtg.editor.section_model import Section, find_section, parse_sections

UNCATEGORIZED_KEY = SectionKey(SectionKind.OTHER, UNCATEGORIZED_LABEL)

# Derived groupings whose duplicates normalization folds together.
# Fixed labels ('// Other') and zone headers are left alone.
_MERGEABLE_KINDS = (SectionKind.TYPE, SectionKind.CATEGORY)


def matched_indent(buf: Buffer, row: int) -> str:
    """Indentation for a card inserted at `row`, matching the enclosing
    Python-style zone block (an unindented line would terminate it)."""
    for i in range(row - 1, -1, -1):
        bl = buf.get_line(i)
        if bl.line_type == LineType.BLANK:
            continue
        if block_header_tag(bl.text) is not None:
            return "    "
        if bl.line_type == LineType.METADATA:
            return ""
        # Cards, headers, and comments all sit at their block's depth —
        # an unindented insert after '    // note' would close the block
        return bl.text[: len(bl.text) - len(bl.text.lstrip())]
    return ""


def section_insert_row(buf: Buffer, key: SectionKey) -> tuple[Buffer, int]:
    """Row where a mainboard card of section `key` belongs.

    Joins the existing section in any spelling; creates the header when
    missing — indented inside the DCK: block when the deck uses one,
    blank-separated at the top level otherwise. New headers are written
    already normalize-stable (blank line before them), so the cleanup
    pass never shifts rows — a shift would leave the caller's cursor
    pointing at the header.
    Returns (buffer, insert_row) — buffer may have new header lines.
    """
    section = find_section(parse_sections(buf), key, LineType.CARD_ENTRY)
    if section is not None:
        return buf, section.insert_row
    return _create_section_row(buf, key)


def type_section_insert_row(
    buf: Buffer, section_name: str
) -> tuple[Buffer, int]:
    """section_insert_row for a type named in any spelling ('Sorcery',
    'Sorceries') or a fixed label ('Other')."""
    return section_insert_row(buf, section_key_for_label(section_name))


def uncategorized_insert_row(buf: Buffer) -> tuple[Buffer, int]:
    """Row where a category-less mainboard card belongs in a
    category-grouped deck: with the other uncategorized cards."""
    return section_insert_row(buf, UNCATEGORIZED_KEY)


def _create_section_row(buf: Buffer, key: SectionKey) -> tuple[Buffer, int]:
    """Create `key`'s header and return the card row under it — indented
    inside the DCK: block when the deck uses one (after the block's
    current content), blank-separated before the sideboard or at the
    end otherwise."""
    dck_row = next(
        (
            i for i in range(buf.line_count())
            if parse_zone_header(buf.get_line(i).text) == "DCK"
        ),
        None,
    )
    if dck_row is not None:
        insert_at = dck_row + 1
        i = dck_row + 1
        while i < buf.line_count():
            bl = buf.get_line(i)
            if bl.line_type == LineType.BLANK:
                i += 1
                continue
            in_block = bl.text[:1].isspace() and bl.line_type in (
                LineType.CARD_ENTRY, LineType.SECTION_HEADER,
            )
            if not in_block:
                break
            insert_at = i + 1
            i += 1
        if buf.get_line(insert_at - 1).line_type != LineType.BLANK:
            buf = buf.insert_line(insert_at, "")
            insert_at += 1
        buf = buf.insert_line(insert_at, key.header_text("    "))
        return buf, insert_at + 1

    # Legacy layout — create the section before sideboard or at end
    insert_at = buf.line_count()
    for i in range(buf.line_count()):
        bl = buf.get_line(i)
        if bl.line_type == LineType.SIDEBOARD_ENTRY:
            insert_at = i
            break

    # Add blank line separator if previous line is content
    if insert_at > 0 and buf.get_line(insert_at - 1).line_type != LineType.BLANK:
        buf = buf.insert_line(insert_at, "")
        insert_at += 1

    buf = buf.insert_line(insert_at, key.header_text())
    return buf, insert_at + 1


# ── Normalization ────────────────────────────────────────────────────


def normalize_sections(buffer: Buffer) -> Buffer:
    """Return a normalized Buffer, or `buffer` itself if already clean."""
    merged = _merge_duplicate_sections(buffer)
    kept = _drop_empty_headers(merged)
    collapsed = _collapse_blank_runs(kept)
    padded = _pad_before_headers(collapsed)

    if [bl.text for bl in buffer.get_lines()] == padded:
        return buffer
    return Buffer.from_text("\n".join(padded) + "\n")


def _first_duplicate(
    sections: tuple[Section, ...],
) -> tuple[Section, Section] | None:
    """(earlier, later) for the first pair of mergeable sections that
    denote the same grouping in the same zone at the same depth."""
    seen: dict[tuple[SectionKey, LineType, str], Section] = {}
    for section in sections:
        if section.key.kind not in _MERGEABLE_KINDS:
            continue
        ident = (section.key, section.zone, section.indent)
        if ident not in seen:
            seen[ident] = section
        elif not section.is_empty:
            # An empty duplicate has nothing to move — cleanup drops it
            return seen[ident], section
    return None


def _merge_duplicate_sections(buffer: Buffer) -> Buffer:
    """Fold '// Sorcery' into an earlier '// Sorceries' (and the like):
    the later section's cards move to the end of the earlier one and
    its header goes. Other lines in the later extent (comments, foreign
    zone lines) stay where they are; the blank-line passes that follow
    tidy the separators."""
    buf = buffer
    while True:
        pair = _first_duplicate(parse_sections(buf))
        if pair is None:
            return buf
        first, later = pair
        texts = [bl.text for bl in buf.get_lines()]
        removing = set(later.card_rows) | {later.header_row}
        moved = [texts[r] for r in later.card_rows]
        remaining = [t for i, t in enumerate(texts) if i not in removing]
        # `first` precedes `later`, so its insert row is unshifted
        remaining[first.insert_row:first.insert_row] = moved
        while remaining and not remaining[-1].strip():
            remaining.pop()  # a removed tail section leaves its separator
        buf = Buffer.from_text("\n".join(remaining) + "\n")


def _would_capture_cards(texts: list[str], header_row: int) -> bool:
    """True when dropping the block-terminating header at `header_row`
    would extend the open zone block over an indented bare card line,
    silently rezoning it."""
    for text in texts[header_row + 1:]:
        if zone_context_effect(text) != "keep":
            return False  # another terminator closes the block first
        if text[:1].isspace() and CARD_PATTERN.match(text) is not None:
            return True
    return False


def _terminates_block(texts: list[str], row: int) -> bool:
    """True when the line at `row` closes an open zone block."""
    return (
        zone_running_context(texts, row) is not None
        and zone_context_effect(texts[row]) == "clear"
    )


def _drop_empty_headers(buffer: Buffer) -> list[tuple[str, LineType]]:
    """Drop derived section headers that hold no cards of their zone.

    Structural zone blocks ('DCK:') are never dropped, and neither is a
    header that is terminating an open zone block above it when removing
    it would swallow the following lines into that block.
    """
    lines = [(bl.text, bl.line_type) for bl in buffer.get_lines()]
    texts = [text for text, _ in lines]
    to_delete: set[int] = set()
    for section in parse_sections(buffer):
        if section.is_structural or not section.is_empty:
            continue
        row = section.header_row
        if _terminates_block(texts, row) and _would_capture_cards(texts, row):
            continue
        to_delete.add(row)
        if row + 1 < len(lines) and lines[row + 1][1] == LineType.BLANK:
            to_delete.add(row + 1)
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
        if line_type in (LineType.SECTION_HEADER, LineType.PLAN_HEADER) and padded:
            prev_type = classify_line(padded[-1])
            if prev_type not in (LineType.BLANK, LineType.METADATA):
                padded.append("")
        padded.append(text)
    return padded

"""Section normalization for deck buffers.

Removes section headers with no cards, collapses runs of blank lines,
and keeps one blank line before each header. Pure buffer-to-buffer
logic; returns the input Buffer unchanged (same object) when the text
is already normalized, so callers can detect "no change" by identity.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from vimtg.domain.deck_lines import (
    apply_zone_effect,
    parse_zone_header,
    zone_context_effect,
)
from vimtg.editor.buffer import (
    LABEL_ZONE_TYPES,
    Buffer,
    LineType,
    classify_line,
)


def matched_indent(buf: Buffer, row: int) -> str:
    """Indentation for a card inserted at `row`, matching the enclosing
    Python-style zone block (an unindented line would terminate it)."""
    for i in range(row - 1, -1, -1):
        bl = buf.get_line(i)
        if bl.line_type == LineType.BLANK:
            continue
        if parse_zone_header(bl.text) is not None:
            return "    "
        if bl.line_type == LineType.METADATA:
            return ""
        # Cards, headers, and comments all sit at their block's depth —
        # an unindented insert after '    // note' would close the block
        return bl.text[: len(bl.text) - len(bl.text.lstrip())]
    return ""


def type_section_insert_row(
    buf: Buffer, section_name: str
) -> tuple[Buffer, int]:
    """Row where a mainboard card of `section_name` type belongs.

    Creates the section header if it doesn't exist — indented inside
    the DCK: block when the deck uses one, blank-separated at the top
    level otherwise. New headers are written already normalize-stable
    (blank line before them), so the cleanup pass never shifts rows —
    a shift would leave the caller's cursor pointing at the header.
    Returns (buffer, insert_row) — buffer may have new header lines.
    """
    # Look for existing section header (indented headers included)
    for i in range(buf.line_count()):
        bl = buf.get_line(i)
        if bl.line_type == LineType.SECTION_HEADER and section_name in bl.text:
            insert_at = i + 1
            while insert_at < buf.line_count() and buf.is_card_line(insert_at):
                insert_at += 1
            return buf, insert_at

    # No matching section. Deck using a DCK: block gets the new
    # section indented inside it, after the block's current content.
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
        buf = buf.insert_line(insert_at, f"    // {section_name}")
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

    buf = buf.insert_line(insert_at, f"// {section_name}")
    return buf, insert_at + 1


def uncategorized_insert_row(buf: Buffer) -> tuple[Buffer, int]:
    """Row where a category-less mainboard card belongs in a
    category-grouped deck: with the other uncategorized cards.

    Joins the existing '// Uncategorized' section when one exists, else
    lands at the top of the DCK: block (above the first category
    section), else at the top of a headerless-block mainboard. Like
    type_section_insert_row, the result is normalize-stable: a blank
    separator is written where the card would otherwise sit directly
    against a following section header.
    Returns (buffer, insert_row) — buffer may have a new blank line.
    """
    from vimtg.domain.categories import UNCATEGORIZED_LABEL

    for i in range(buf.line_count()):
        bl = buf.get_line(i)
        if (
            bl.line_type == LineType.SECTION_HEADER
            and bl.text.strip().removeprefix("//").strip()
            == UNCATEGORIZED_LABEL
        ):
            insert_at = i + 1
            while insert_at < buf.line_count() and buf.is_card_line(insert_at):
                insert_at += 1
            return buf, insert_at

    dck_row = next(
        (
            i for i in range(buf.line_count())
            if parse_zone_header(buf.get_line(i).text) == "DCK"
        ),
        None,
    )
    if dck_row is not None:
        insert_at = dck_row + 1
    else:
        insert_at = next(
            (
                i for i in range(buf.line_count())
                if buf.get_line(i).line_type
                in (LineType.SECTION_HEADER, LineType.CARD_ENTRY)
            ),
            buf.line_count(),
        )
    if (
        insert_at < buf.line_count()
        and buf.get_line(insert_at).line_type == LineType.SECTION_HEADER
    ):
        buf = buf.insert_line(insert_at, "")
    return buf, insert_at


def _expected_card_type(header_text: str) -> LineType | None:
    """The card LineType a header's section is made of.

    None for bare zone block headers ('DCK:', 'CMD:', ...) — those are
    structural zone declarations, not derived groupings, and are never
    auto-dropped.
    """
    if parse_zone_header(header_text) is not None:
        return None
    label = header_text.strip().removeprefix("//").strip()
    return LABEL_ZONE_TYPES.get(label, LineType.CARD_ENTRY)


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


def _would_capture_cards(
    lines: list[tuple[str, LineType]], header_row: int
) -> bool:
    """True when dropping the block-terminating header at `header_row`
    would extend the open zone block over an indented bare card line,
    silently rezoning it."""
    from vimtg.domain.deck_lines import CARD_PATTERN

    for text, _ in lines[header_row + 1:]:
        if zone_context_effect(text) != "keep":
            return False  # another terminator closes the block first
        if text[:1].isspace() and CARD_PATTERN.match(text) is not None:
            return True
    return False


def _drop_empty_headers(
    lines: list[tuple[str, LineType]],
) -> list[tuple[str, LineType]]:
    """Drop section headers with no card lines before the next section.

    Zone-aware: a '// Creature' header is only occupied by mainboard
    cards — a CMD:/SB: line sitting where the section's cards used to
    be does not keep it alive. Blank lines and comments between the
    header and its cards are looked through, and a header that is
    terminating an open zone block above it is never dropped (removing
    it would extend that block over the following lines).
    """
    running: str | None = None
    to_delete: set[int] = set()
    for i, (text, line_type) in enumerate(lines):
        terminates_block = (
            running is not None and zone_context_effect(text) == "clear"
        )
        running = apply_zone_effect(zone_context_effect(text), running)
        if line_type != LineType.SECTION_HEADER:
            continue
        expected = _expected_card_type(text)
        if expected is None:
            continue  # bare zone block header — structural, keep
        if terminates_block and _would_capture_cards(lines, i):
            continue  # dropping it would swallow lines into the block
        has_cards = False
        for _, next_type in lines[i + 1:]:
            if next_type in (LineType.BLANK, LineType.COMMENT):
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

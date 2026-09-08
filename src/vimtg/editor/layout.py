"""Deck layout regrouping — toggle between type and category views.

The deck is a text buffer, so a layout is a property of the text
itself: regrouping rewrites the mainboard under new section headers
(an undoable edit, like :sort), it is not a render-time projection.
Each card's category travels with it as an inline '@name' token, so
toggling back and forth is lossless.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from typing import Any

from vimtg.domain.card_types import TYPE_ORDER, primary_type
from vimtg.domain.categories import UNCATEGORIZED_LABEL
from vimtg.domain.deck_lines import parse_zone_header
from vimtg.domain.section_keys import ZONE_LABELS, SectionKey, SectionKind
from vimtg.editor.buffer import Buffer, BufferLine, LineType
from vimtg.editor.section_model import parse_sections, section_at
from vimtg.editor.sort_keys import extract_card_name, extract_sort_key

LAYOUT_TYPE = "type"
LAYOUT_CATEGORY = "category"
LAYOUT_MODES = (LAYOUT_TYPE, LAYOUT_CATEGORY)


def detect_layout(buffer: Buffer) -> str:
    """Infer the buffer's current layout from its section headers.

    Any '// @name' category header means the deck is category-grouped;
    otherwise it is treated as type-grouped (the conventional default).
    """
    if any(
        section.key.kind is SectionKind.CATEGORY
        for section in parse_sections(buffer)
    ):
        return LAYOUT_CATEGORY
    return LAYOUT_TYPE


def enclosing_category(buffer: Buffer, row: int) -> str:
    """Category of the section containing `row` ('' when none).

    Only a '// @name' section yields a category — a type section (or
    no section) yields ''.
    """
    # An insert at the very end (row == line count) belongs to the
    # section that runs to the end
    row = min(row, buffer.line_count() - 1)
    section = section_at(parse_sections(buffer), row)
    if section is not None and section.key.kind is SectionKind.CATEGORY:
        return section.key.ident
    return ""


def regroup_buffer(
    buffer: Buffer,
    mode: str,
    resolved_cards: dict[str, Any] | None = None,
    order_field: str = "cmc",
    price_source: str = "usd",
) -> Buffer:
    """Rewrite the buffer grouped by card type or by category.

    Metadata lines stay at the top; freeform comments are kept after
    them (their positions inside the list are not preserved — same
    normalization :import and merge already apply). Mainboard cards
    are regrouped under fresh section headers and ordered by
    `order_field` within each group. Commander, companion, sideboard,
    and maybeboard cards keep their zones as separate blocks, and each
    zone keeps its style: a Python-style block ('CMD:' with indented
    cards) stays a block, prefix lines stay prefixed. Sideboard plans
    ('VS:' blocks) are carried over byte-for-byte, after every zone.
    """
    if mode not in LAYOUT_MODES:
        raise ValueError(f"Unknown layout mode: {mode}")

    metadata: list[str] = []
    comments: list[str] = []
    block_tags: set[str] = set()
    zone_lines: dict[LineType, list[BufferLine]] = {
        LineType.COMMANDER_ENTRY: [],
        LineType.COMPANION_ENTRY: [],
        LineType.CARD_ENTRY: [],
        LineType.SIDEBOARD_ENTRY: [],
        LineType.MAYBEBOARD_ENTRY: [],
    }

    plan_tail, plan_rows = _plan_blocks_verbatim(buffer)

    for i in range(buffer.line_count()):
        if i in plan_rows:
            continue
        bl = buffer.get_line(i)
        tag = parse_zone_header(bl.text)
        if tag is not None:
            block_tags.add(tag)
        elif bl.line_type == LineType.METADATA:
            metadata.append(bl.text)
        elif bl.line_type == LineType.COMMENT:
            comments.append(bl.text)
        elif bl.line_type in zone_lines:
            zone_lines[bl.line_type].append(bl)
        # Section headers and blanks are rebuilt, not carried over

    resolved = resolved_cards or {}

    def sort_group(group: list[BufferLine]) -> list[BufferLine]:
        return sorted(
            group,
            key=lambda bl: extract_sort_key(
                bl, order_field, resolved, price_source=price_source
            ),
        )

    if mode == LAYOUT_TYPE:
        groups = _group_by_type(zone_lines[LineType.CARD_ENTRY], resolved)
    else:
        groups = _group_by_category(zone_lines[LineType.CARD_ENTRY])

    out: list[str] = list(metadata)
    if comments:
        _pad(out)
        out.extend(comments)

    def emit_zone(
        tag: str, label: str, entries: list[BufferLine], sort: bool
    ) -> None:
        if not entries:
            # An empty block header is a structural declaration (like a
            # scaffolded CMD:) — regrouping must not delete it when
            # section cleanup deliberately preserves it
            if tag in block_tags:
                _pad(out)
                out.append(f"{tag}:")
            return
        ordered = sort_group(entries) if sort else entries
        _pad(out)
        if tag in block_tags:
            out.append(f"{tag}:")
            out.extend(f"    {_bare(bl.text, tag)}" for bl in ordered)
        else:
            out.append(f"// {label}")
            out.extend(_prefixed(bl.text, f"{tag}: ") for bl in ordered)

    emit_zone("CMD", ZONE_LABELS["CMD"], zone_lines[LineType.COMMANDER_ENTRY], False)
    emit_zone("CMP", ZONE_LABELS["CMP"], zone_lines[LineType.COMPANION_ENTRY], False)

    dck_block = "DCK" in block_tags
    if dck_block:
        _pad(out)
        out.append("DCK:")
    for header, group in groups:
        if not group:
            continue
        _pad(out)
        indent = "    " if dck_block else ""
        out.append(f"{indent}{header}")
        out.extend(
            f"{indent}{bl.text.strip()}" if indent else bl.text
            for bl in sort_group(group)
        )

    emit_zone("SB", ZONE_LABELS["SB"], zone_lines[LineType.SIDEBOARD_ENTRY], True)
    emit_zone("MB", ZONE_LABELS["MB"], zone_lines[LineType.MAYBEBOARD_ENTRY], True)

    if plan_tail:
        _pad(out)
        out.extend(plan_tail)

    return Buffer.from_text("\n".join(out) + "\n")


def follow_line(old_buf: Buffer, new_buf: Buffer, row: int) -> int:
    """Row in `new_buf` of the line that sat at `row` in `old_buf`.

    Regrouping, normalization, and category refiling move whole lines
    without editing them, so the line is refound by matching its text
    occurrence count. Falls back to `row` (callers clamp) for blank or
    dropped lines.
    """
    if row >= old_buf.line_count():
        return row
    text = old_buf.get_line(row).text
    if not text.strip():
        return row
    nth = sum(1 for i in range(row + 1) if old_buf.get_line(i).text == text)
    seen = 0
    for i in range(new_buf.line_count()):
        if new_buf.get_line(i).text == text:
            seen += 1
            if seen == nth:
                return i
    return row


def regroup_following_cursor(
    buffer: Buffer,
    row: int,
    mode: str,
    resolved_cards: dict[str, Any] | None,
    order_field: str,
    price_source: str,
) -> tuple[Buffer, int]:
    """regroup_buffer plus the cursor's new row, clamped."""
    new_buf = regroup_buffer(buffer, mode, resolved_cards, order_field, price_source)
    new_row = follow_line(buffer, new_buf, row)
    return new_buf, min(new_row, max(0, new_buf.line_count() - 1))


def _plan_blocks_verbatim(buffer: Buffer) -> tuple[list[str], set[int]]:
    """(lines, rows) of every 'VS:' plan block, text unchanged.

    A block runs from its header through every following indented or
    blank line (comments inside it included); trailing blanks are
    trimmed and blocks are re-separated by one blank line.
    """
    tail: list[str] = []
    rows: set[int] = set()
    i = 0
    count = buffer.line_count()
    while i < count:
        bl = buffer.get_line(i)
        if bl.line_type != LineType.PLAN_HEADER:
            i += 1
            continue
        span = [bl.text]
        rows.add(i)
        j = i + 1
        while j < count:
            nxt = buffer.get_line(j)
            if nxt.line_type != LineType.BLANK and not nxt.text[:1].isspace():
                break
            span.append(nxt.text)
            rows.add(j)
            j += 1
        while span and not span[-1].strip():
            span.pop()
        if tail:
            tail.append("")
        tail.extend(span)
        i = j
    return tail, rows


def _pad(out: list[str]) -> None:
    """Blank-line separator before a new block (skipped at the top)."""
    if out and out[-1] != "":
        out.append("")


def _prefixed(text: str, prefix: str) -> str:
    """Canonicalize a zone line to prefix style for the regrouped file.

    Regrouping rewrites the buffer without the Python-style block
    headers, so a bare 'CMD:'-block line must regain its explicit
    prefix or it would reclassify as mainboard.
    """
    stripped = text.strip()
    if stripped.upper().startswith(prefix.strip().upper()):
        return stripped
    return f"{prefix}{stripped}"


def _bare(text: str, tag: str) -> str:
    """Strip a zone line to bare form for emission inside its block."""
    stripped = text.strip()
    if stripped.upper().startswith(f"{tag}:"):
        stripped = stripped[len(tag) + 1:].lstrip()
    return stripped


_OTHER_KEY = SectionKey(SectionKind.OTHER, "Other")
_UNCATEGORIZED_KEY = SectionKey(SectionKind.OTHER, UNCATEGORIZED_LABEL)


def _type_key(ptype: str | None) -> SectionKey:
    return SectionKey(SectionKind.TYPE, ptype) if ptype else _OTHER_KEY


def _group_by_type(
    cards: list[BufferLine], resolved: dict[str, Any]
) -> list[tuple[str, list[BufferLine]]]:
    """Group mainboard lines by primary card type, in canonical order."""
    buckets: dict[SectionKey, list[BufferLine]] = {}
    for bl in cards:
        card = resolved.get(extract_card_name(bl.text.strip()))
        ptype = primary_type(card.type_line) if card is not None else None
        buckets.setdefault(_type_key(ptype), []).append(bl)

    def type_rank(key: SectionKey) -> int:
        return TYPE_ORDER.get(key.ident, 99) if key.kind is SectionKind.TYPE else 99

    return [
        (key.header_text(), buckets[key])
        for key in sorted(buckets, key=type_rank)
    ]


def _group_by_category(
    cards: list[BufferLine],
) -> list[tuple[str, list[BufferLine]]]:
    """Group mainboard lines by category, in first-appearance order.

    First-appearance order preserves the user's own arrangement across
    toggles; uncategorized cards form a trailing group.
    """
    from vimtg.domain.deck_lines import parse_card_parts
    from vimtg.editor.sort_keys import match_card_line

    buckets: dict[str, list[BufferLine]] = {}
    order: list[str] = []
    uncategorized: list[BufferLine] = []
    for bl in cards:
        m = match_card_line(bl.text.strip())
        category = parse_card_parts(m.group(2))[1] if m else ""
        if not category:
            uncategorized.append(bl)
            continue
        if category not in buckets:
            buckets[category] = []
            order.append(category)
        buckets[category].append(bl)

    groups = [
        (SectionKey(SectionKind.CATEGORY, category).header_text(), buckets[category])
        for category in order
    ]
    if uncategorized:
        groups.append((_UNCATEGORIZED_KEY.header_text(), uncategorized))
    return groups

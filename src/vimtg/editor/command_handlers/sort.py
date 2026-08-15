"""Sort command: :sort [field] — TUI-agnostic, zero Textual imports.

Sorts card entry lines within a range or current section.
Non-card lines (comments, section headers, blanks) stay anchored in place.
"""

from __future__ import annotations

from typing import Any

from vimtg.domain.card import Color
from vimtg.domain.card_types import TYPE_ORDER, primary_type
from vimtg.domain.deck_lines import (
    CARD_PATTERN,
    CMD_PATTERN,
    MB_PATTERN,
    SB_PATTERN,
    parse_card_suffix,
    split_inline_comment,
)
from vimtg.domain.tags import parse_inline_tags
from vimtg.editor.buffer import CARD_LINE_TYPES, Buffer, BufferLine, classify_line
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
    resolve_command_range,
)
from vimtg.editor.cursor import Cursor

_COLOR_ORDER: dict[str, int] = {c.value: i for i, c in enumerate(Color)}


def _extract_sort_key(
    line: BufferLine,
    sort_field: str,
    resolved_cards: dict[str, Any] | None = None,
) -> tuple[float, str]:
    """Extract a sort key from a card line based on the requested field.

    Always returns a consistent 2-tuple (numeric_key, name_fallback) so
    sorted() never compares mismatched shapes.
    """
    text = line.text.strip()
    card_name = _extract_card_name(text)
    card = resolved_cards.get(card_name) if resolved_cards else None
    fallback = card_name.lower()

    if sort_field == "qty":
        m = _match_card_line(text)
        return (int(m.group(1)) if m else 0, fallback)

    if sort_field == "cmc":
        return (card.cmc if card is not None else 9999.0, fallback)

    if sort_field == "type":
        if card is None:
            return (99, fallback)
        ptype = primary_type(card.type_line)
        return (TYPE_ORDER.get(ptype, 99) if ptype else 99, fallback)

    if sort_field == "color":
        if card is None:
            return (99, fallback)
        colors = card.colors or []
        if not colors:
            return (99, fallback)
        if len(colors) > 1:
            return (10 + len(colors), fallback)
        color_val = (
            colors[0].value if hasattr(colors[0], "value")
            else str(colors[0])
        )
        return (_COLOR_ORDER.get(color_val, 98), fallback)

    if sort_field == "tag":
        # '#word' inside an inline comment is prose, not a tag
        tags = parse_inline_tags(split_inline_comment(text)[0])
        if not tags:
            return (1, fallback)  # untagged cards sort after tagged
        first_tag = sorted(tags)[0]
        return (0, first_tag + "|" + fallback)

    # "name" — sort alphabetically, all at same numeric priority
    return (0, fallback)


def _match_card_line(text: str):  # type: ignore[no-untyped-def]
    """Match a card line against the shared deck-line grammar."""
    for pattern in (SB_PATTERN, MB_PATTERN, CMD_PATTERN, CARD_PATTERN):
        m = pattern.match(text)
        if m:
            return m
    return None


def _extract_card_name(text: str) -> str:
    """Extract card name from a line, stripping quantity, prefix, tags, and comment."""
    m = _match_card_line(text)
    raw = m.group(2) if m else text
    return parse_card_suffix(raw)[0]


def _resolve_range(
    buffer: Buffer, cmd: ParsedCommand, cursor_row: int
) -> tuple[int, int] | None:
    """Determine the line range to sort (default: current section)."""
    explicit = resolve_command_range(cmd)
    if explicit is not None:
        return explicit
    return buffer.section_range(cursor_row)


def cmd_sort(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:sort [field] — Sort card lines within range or current section.

    Fields: name (default), qty, cmc, type, color, tag.
    :sort! reverses the order.
    Only sorts card entry lines; comments and blanks stay anchored.
    """
    sort_field = cmd.args.strip().lower() if cmd.args else "name"
    valid_fields = {"name", "qty", "cmc", "type", "color", "tag"}

    if sort_field and sort_field not in valid_fields:
        ctx.fail(f"Unknown sort field: {sort_field}")
        return buffer, cursor

    # cmc, type, color fall back to name when card data unavailable
    if sort_field in {"cmc", "type", "color"} and not ctx.resolved_cards:
        ctx.message = "Card data not available; sorting by name"
        sort_field = "name"

    resolved = _resolve_range(buffer, cmd, cursor.row)
    if resolved is None:
        ctx.fail("No card section to sort")
        return buffer, cursor

    start, end = resolved
    lines = list(buffer.get_lines())
    region = lines[start : end + 1]

    # Separate card lines from non-card anchored lines
    card_entries: list[tuple[int, BufferLine]] = []
    anchored: dict[int, BufferLine] = {}

    for offset, bl in enumerate(region):
        if bl.line_type in CARD_LINE_TYPES:
            card_entries.append((offset, bl))
        else:
            anchored[offset] = bl

    if not card_entries:
        ctx.message = "No card lines to sort"
        return buffer, cursor

    # Sort the card entries
    card_data = ctx.resolved_cards or {}
    sorted_cards = sorted(
        [bl for _, bl in card_entries],
        key=lambda bl: _extract_sort_key(bl, sort_field, card_data),
        reverse=cmd.bang,
    )

    # Reassemble: anchored lines stay, card slots get sorted entries
    result: list[BufferLine] = []
    card_idx = 0
    for offset in range(len(region)):
        if offset in anchored:
            result.append(anchored[offset])
        else:
            result.append(sorted_cards[card_idx])
            card_idx += 1

    # Build new lines tuple
    new_lines = (
        tuple(lines[:start])
        + tuple(result)
        + tuple(lines[end + 1 :])
    )
    new_buffer = Buffer(
        tuple(
            BufferLine(text=bl.text, line_type=classify_line(bl.text))
            for bl in new_lines
        )
    )

    count = len(sorted_cards)
    ctx.message = f"Sorted {count} card{'s' if count != 1 else ''} by {sort_field}"
    return new_buffer, cursor


def register_sort_commands(registry: CommandRegistry) -> None:
    """Register the :sort command."""
    registry.register("sort", cmd_sort)

"""Sort command: :sort [field] — TUI-agnostic, zero Textual imports.

Sorts card entry lines within a range or current section.
Non-card lines (comments, section headers, blanks) stay anchored in place.
"""

from __future__ import annotations

from typing import Any

from vimtg.domain.tags import parse_inline_tags, strip_inline_tags
from vimtg.editor.buffer import Buffer, BufferLine, LineType, classify_line
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor

_CARD_LINE_TYPES = frozenset({
    LineType.CARD_ENTRY,
    LineType.SIDEBOARD_ENTRY,
    LineType.COMMANDER_ENTRY,
})


_TYPE_ORDER: dict[str, int] = {
    "Creature": 0,
    "Planeswalker": 1,
    "Instant": 2,
    "Sorcery": 3,
    "Enchantment": 4,
    "Artifact": 5,
    "Land": 6,
}

_COLOR_ORDER: dict[str, int] = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}


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
        parts = text.split(None, 1)
        if parts and parts[0].isdigit():
            return (int(parts[0]), fallback)
        if text.startswith(("SB:", "CMD:")):
            rest = text.split(":", 1)[1].strip()
            qty_parts = rest.split(None, 1)
            if qty_parts and qty_parts[0].isdigit():
                return (int(qty_parts[0]), fallback)
        return (0, fallback)

    if sort_field == "cmc":
        return (card.cmc if card is not None else 9999.0, fallback)

    if sort_field == "type":
        if card is None:
            return (99, fallback)
        front = card.type_line.split("—")[0].split("//")[0].strip()
        order = 99
        for tname, tord in _TYPE_ORDER.items():
            if tname in front:
                order = tord
                break
        return (order, fallback)

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
        tags = parse_inline_tags(text)
        if not tags:
            return (1, fallback)  # untagged cards sort after tagged
        first_tag = sorted(tags)[0]
        return (0, first_tag + "|" + fallback)

    # "name" — sort alphabetically, all at same numeric priority
    return (0, fallback)


def _extract_card_name(text: str) -> str:
    """Extract card name from a line, stripping quantity, prefix, and inline tags."""
    # SB: N CardName or CMD: N CardName
    if text.startswith(("SB:", "CMD:")):
        rest = text.split(":", 1)[1].strip()
        parts = rest.split(None, 1)
        raw = parts[1] if len(parts) > 1 else rest
        return strip_inline_tags(raw).strip()

    # N CardName
    parts = text.split(None, 1)
    if len(parts) > 1 and parts[0].isdigit():
        return strip_inline_tags(parts[1]).strip()
    return strip_inline_tags(text).strip()


def _resolve_range(
    buffer: Buffer, cmd: ParsedCommand, cursor_row: int
) -> tuple[int, int] | None:
    """Determine the line range to sort."""
    if cmd.cmd_range is not None and cmd.cmd_range.start is not None:
        return (cmd.cmd_range.start, cmd.cmd_range.end or cmd.cmd_range.start)

    # No explicit range: sort current section
    return buffer.section_range(cursor_row)


def cmd_sort(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:sort [field] — Sort card lines within range or current section.

    Fields: name (default), qty.
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
        if bl.line_type in _CARD_LINE_TYPES:
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

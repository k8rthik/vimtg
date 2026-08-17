"""Sort command: :sort [field] — TUI-agnostic, zero Textual imports.

Sorts card entry lines within a range or current section.
Non-card lines (comments, section headers, blanks) stay anchored in place.
Key extraction lives in vimtg.editor.sort_keys, shared with the layout
regrouper so ordering means the same thing everywhere.
"""

from __future__ import annotations

from vimtg.editor.buffer import (
    CARD_LINE_TYPES,
    Buffer,
    BufferLine,
    LineType,
    classify_lines,
)
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
    resolve_command_range,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.sort_keys import (
    CARD_DATA_FIELDS,
    SORT_FIELDS,
    extract_sort_key,
)


def _resolve_range(
    buffer: Buffer, cmd: ParsedCommand, cursor_row: int
) -> tuple[int, int] | None:
    """Determine the line range to sort (default: current section)."""
    explicit = resolve_command_range(cmd)
    if explicit is not None:
        return explicit
    return buffer.section_range(cursor_row)


def default_sort_field(ctx: EditorContext) -> str:
    """The sort_order setting, guarded against missing/invalid values."""
    field = getattr(ctx.settings, "sort_order", "") or ""
    return field if field in SORT_FIELDS else "name"


def cmd_sort(
    buffer: Buffer,
    cursor: Cursor,
    cmd: ParsedCommand,
    ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:sort [field] — Sort card lines within range or current section.

    Fields: name, qty, cmc, type, color, tag, category, power,
    toughness, rarity, price. Without a field, the sort_order setting
    decides (default: cmc). :sort! reverses the order.
    Only sorts card entry lines; comments and blanks stay anchored.
    """
    sort_field = cmd.args.strip().lower() if cmd.args else default_sort_field(ctx)

    if sort_field and sort_field not in SORT_FIELDS:
        ctx.fail(f"Unknown sort field: {sort_field}")
        return buffer, cursor

    # Card-data fields fall back to name when card data unavailable
    if sort_field in CARD_DATA_FIELDS and not ctx.resolved_cards:
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

    # Sort per zone: a range can span zone boundaries (an indented
    # commander line next to an SB: prefix line), and reordering across
    # them would move lines past a block terminator, changing zones.
    # Each card slot keeps its original zone; entries sort within it.
    card_data = ctx.resolved_cards or {}
    price_source = getattr(ctx.settings, "price_source", "usd") or "usd"
    by_zone: dict[LineType, list[BufferLine]] = {}
    for _, bl in card_entries:
        by_zone.setdefault(bl.line_type, []).append(bl)
    sorted_by_zone = {
        zone: sorted(
            entries,
            key=lambda bl: extract_sort_key(
                bl, sort_field, card_data, price_source=price_source
            ),
            reverse=cmd.bang,
        )
        for zone, entries in by_zone.items()
    }
    zone_idx = dict.fromkeys(sorted_by_zone, 0)

    # Reassemble: anchored lines stay, card slots get sorted entries
    result: list[BufferLine] = []
    for offset, bl in enumerate(region):
        if offset in anchored:
            result.append(anchored[offset])
        else:
            zone = bl.line_type
            result.append(sorted_by_zone[zone][zone_idx[zone]])
            zone_idx[zone] += 1

    # Rebuild with zone-block context — per-line classification would
    # demote indented block cards to mainboard in the live session
    new_texts = [bl.text for bl in lines[:start]]
    new_texts += [bl.text for bl in result]
    new_texts += [bl.text for bl in lines[end + 1:]]
    new_buffer = Buffer(classify_lines(new_texts))

    count = len(card_entries)
    ctx.message = f"Sorted {count} card{'s' if count != 1 else ''} by {sort_field}"
    return new_buffer, cursor


def register_sort_commands(registry: CommandRegistry) -> None:
    """Register the :sort command."""
    registry.register("sort", cmd_sort)

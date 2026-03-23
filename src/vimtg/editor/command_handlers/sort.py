"""Sort command: :sort [field] — TUI-agnostic, zero Textual imports.

Sorts card entry lines within a range or current section.
Non-card lines (comments, section headers, blanks) stay anchored in place.
"""

from __future__ import annotations

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


def _extract_sort_key(line: BufferLine, sort_field: str) -> str | int:
    """Extract a sort key from a card line based on the requested field."""
    text = line.text.strip()

    if sort_field == "qty":
        # Extract numeric quantity prefix
        parts = text.split(None, 1)
        if parts and parts[0].isdigit():
            return int(parts[0])
        # Handle SB:/CMD: prefix
        if text.startswith(("SB:", "CMD:")):
            rest = text.split(":", 1)[1].strip()
            qty_parts = rest.split(None, 1)
            if qty_parts and qty_parts[0].isdigit():
                return int(qty_parts[0])
        return 0

    # Default: sort by card name (alphabetical)
    return _extract_card_name(text).lower()


def _extract_card_name(text: str) -> str:
    """Extract card name from a line, stripping quantity and prefix."""
    # SB: N CardName or CMD: N CardName
    if text.startswith(("SB:", "CMD:")):
        rest = text.split(":", 1)[1].strip()
        parts = rest.split(None, 1)
        return parts[1] if len(parts) > 1 else rest

    # N CardName
    parts = text.split(None, 1)
    if len(parts) > 1 and parts[0].isdigit():
        return parts[1]
    return text


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
    valid_fields = {"name", "qty", "cmc", "type", "color"}

    if sort_field and sort_field not in valid_fields:
        ctx.message = f"Unknown sort field: {sort_field}"
        ctx.error = True
        return buffer, cursor

    # cmc, type, color fall back to name until card resolution is available
    if sort_field in {"cmc", "type", "color"}:
        sort_field = "name"

    resolved = _resolve_range(buffer, cmd, cursor.row)
    if resolved is None:
        ctx.message = "No card section to sort"
        ctx.error = True
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
    sorted_cards = sorted(
        [bl for _, bl in card_entries],
        key=lambda bl: _extract_sort_key(bl, sort_field),
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

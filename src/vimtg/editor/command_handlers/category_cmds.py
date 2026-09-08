"""Category commands: :category (:cat), :categories, :layout.

TUI-agnostic: zero Textual imports.
"""

from __future__ import annotations

from vimtg.config.category_history import record_category
from vimtg.domain.categories import (
    CATEGORY_NAME_RE,
    format_category_summary,
)
from vimtg.editor.buffer import Buffer
from vimtg.editor.category_ops import (
    clear_category_in_range,
    set_category_in_range,
)
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
    resolve_command_range,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.layout import (
    LAYOUT_CATEGORY,
    LAYOUT_MODES,
    LAYOUT_TYPE,
    detect_layout,
    follow_line,
    regroup_following_cursor,
)
from vimtg.editor.placement import reconcile_category_sections


def _card_range(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand,
) -> tuple[int, int]:
    """No range → cursor line only, matching the tag commands."""
    explicit = resolve_command_range(cmd)
    return explicit if explicit is not None else (cursor.row, cursor.row)


def cmd_category(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:category name — set category. :category! — clear. :category — show."""
    start, end = _card_range(buf, cursor, cmd)

    if cmd.bang:
        buf, count = clear_category_in_range(buf, start, end)
        if count:
            buf, cursor = _refile(buf, cursor)
            ctx.message = f"Cleared category from {count} card(s)"
            ctx.modified = True
        else:
            ctx.message = "No categorized cards in range"
        return buf, cursor

    name = cmd.args.strip().lstrip("@").lower()
    if not name:
        current = buf.category_at(cursor.row)
        ctx.message = f"Category: @{current}" if current else "No category"
        return buf, cursor

    if not CATEGORY_NAME_RE.match(name):
        ctx.fail(
            f"Invalid category: '{name}' (letters, digits, hyphens; 1-32 chars)"
        )
        return buf, cursor

    buf, count = set_category_in_range(buf, start, end, name)
    if count == 0:
        ctx.message = "No card lines in range"
    else:
        buf, cursor = _refile(buf, cursor)
        ctx.message = f"Categorized {count} card(s) as @{name}"
        ctx.modified = True
        record_category(name)
    return buf, cursor


def _refile(buf: Buffer, cursor: Cursor) -> tuple[Buffer, Cursor]:
    """Move re-categorized cards under their headers (category layout
    only); the cursor follows its line."""
    refiled = reconcile_category_sections(buf)
    if refiled is buf:
        return buf, cursor
    row = follow_line(buf, refiled, cursor.row)
    return refiled, cursor.move_to(min(row, max(0, refiled.line_count() - 1)), 0)


def cmd_categories(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:categories — list categories. :categories name — list its cards."""
    if cmd.args.strip():
        category = cmd.args.strip().lstrip("@").lower()
        matches: list[str] = []
        for line in range(buf.line_count()):
            if buf.category_at(line) == category:
                name = buf.card_name_at(line)
                if name:
                    matches.append(name)
        if matches:
            ctx.message = f"@{category}: {', '.join(matches)}"
        else:
            ctx.message = f"No cards in category @{category}"
        return buf, cursor

    ctx.message = format_category_summary(buf.category_counts())
    return buf, cursor


def apply_layout(
    buf: Buffer, cursor: Cursor, mode: str, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """Regroup the buffer into `mode` layout, preserving the cursor card."""
    order_field = getattr(ctx.settings, "sort_order", "cmc") or "cmc"
    price_source = getattr(ctx.settings, "price_source", "usd") or "usd"
    new_buf, new_row = regroup_following_cursor(
        buf, cursor.row, mode, ctx.resolved_cards, order_field, price_source
    )
    new_cursor = cursor.move_to(new_row, 0)

    ctx.modified = True
    label = "category" if mode == LAYOUT_CATEGORY else "type"
    ctx.message = f"Layout: by {label} (ordered by {order_field})"
    return new_buf, new_cursor


def cmd_layout(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:layout [type|category] — regroup the deck; no argument toggles."""
    arg = cmd.args.strip().lower()
    if arg and arg not in LAYOUT_MODES:
        ctx.fail("Usage: :layout [type|category]")
        return buf, cursor

    mode = arg or (
        LAYOUT_TYPE
        if detect_layout(buf) == LAYOUT_CATEGORY
        else LAYOUT_CATEGORY
    )

    if mode == LAYOUT_TYPE and not ctx.resolved_cards:
        ctx.fail("Card data not available for type layout")
        return buf, cursor

    return apply_layout(buf, cursor, mode, ctx)


def register_category_commands(registry: CommandRegistry) -> None:
    """Register the category and layout ex commands."""
    registry.register("category", cmd_category, aliases=["cat"])
    registry.register("categories", cmd_categories, aliases=["cats"])
    registry.register("layout", cmd_layout)

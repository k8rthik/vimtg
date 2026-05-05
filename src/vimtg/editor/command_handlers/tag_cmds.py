"""Tag commands: :tag, :untag, :tags, :dtag, :duntag, :filter, :retag.

TUI-agnostic: zero Textual imports.
"""

from __future__ import annotations

import re
from typing import Any

from vimtg.domain.tags import (
    TagFilter,
    format_inline_tags,
    matches_filter,
    parse_inline_tags,
    parse_tag_filter,
)
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor

_TAG_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]{0,31}$")

_CARD_LINE_TYPES = frozenset({
    LineType.CARD_ENTRY,
    LineType.SIDEBOARD_ENTRY,
    LineType.COMMANDER_ENTRY,
})


def _validate_tag_names(raw: str) -> tuple[list[str], str | None]:
    """Parse and validate space-separated tag names. Returns (tags, error)."""
    names = [n.lstrip("#").lower() for n in raw.split() if n.lstrip("#")]
    if not names:
        return [], "No tag name provided"
    for name in names:
        if not _TAG_NAME_RE.match(name):
            return [], f"Invalid tag: '{name}' (letters, digits, hyphens; 1-32 chars)"
    return names, None


def _card_range(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand,
) -> tuple[int, int]:
    """Resolve the line range for a tag command.

    No range → cursor line only. Range → start..end inclusive.
    """
    if cmd.cmd_range is not None and cmd.cmd_range.start is not None:
        return cmd.cmd_range.start, cmd.cmd_range.end or cmd.cmd_range.start
    return cursor.row, cursor.row


def cmd_tag(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:tag name [name2...] — add tag(s) to card(s)."""
    names, err = _validate_tag_names(cmd.args)
    if err:
        ctx.message = err
        ctx.error = True
        return buf, cursor

    start, end = _card_range(buf, cursor, cmd)
    count = 0
    for line in range(start, end + 1):
        if buf.is_card_line(line):
            for name in names:
                buf = buf.add_tag(line, name)
            count += 1

    if count == 0:
        ctx.message = "No card lines in range"
    else:
        tag_str = " ".join(f"#{n}" for n in names)
        ctx.message = f"Tagged {count} card(s) with {tag_str}"
        ctx.modified = True
    return buf, cursor


def cmd_untag(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:untag name — remove tag. :untag! — remove ALL tags."""
    start, end = _card_range(buf, cursor, cmd)

    if cmd.bang:
        count = 0
        for line in range(start, end + 1):
            if buf.is_card_line(line) and buf.tags_at(line):
                buf = buf.set_tags(line, frozenset())
                count += 1
        ctx.message = f"Cleared tags from {count} card(s)" if count else "No tagged cards in range"
        if count:
            ctx.modified = True
        return buf, cursor

    names, err = _validate_tag_names(cmd.args)
    if err:
        ctx.message = err
        ctx.error = True
        return buf, cursor

    count = 0
    for line in range(start, end + 1):
        if buf.is_card_line(line):
            for name in names:
                if name in buf.tags_at(line):
                    buf = buf.remove_tag(line, name)
                    count += 1

    if count == 0:
        ctx.message = "No matching tags found"
    else:
        ctx.message = f"Removed {count} tag(s)"
        ctx.modified = True
    return buf, cursor


def cmd_tags(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:tags — list all tags. :tags name — list cards with tag."""
    if cmd.args.strip():
        # List cards with a specific tag
        tag = cmd.args.strip().lstrip("#").lower()
        matches: list[str] = []
        for line in range(buf.line_count()):
            if tag in buf.tags_at(line):
                name = buf.card_name_at(line)
                if name:
                    matches.append(name)
        if matches:
            ctx.message = f"#{tag}: {', '.join(matches)}"
        else:
            ctx.message = f"No cards with tag #{tag}"
        return buf, cursor

    # List all tags with counts
    tag_counts: dict[str, int] = {}
    for line in range(buf.line_count()):
        for tag in buf.tags_at(line):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    if not tag_counts:
        ctx.message = "No tags in deck"
        return buf, cursor

    parts = [f"#{t}({c})" for t, c in sorted(tag_counts.items())]
    ctx.message = f"Tags: {' '.join(parts)}"
    return buf, cursor


def cmd_dtag(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:dtag name [name2...] — add deck-level tags via // Tags: metadata."""
    names, err = _validate_tag_names(cmd.args)
    if err:
        ctx.message = err
        ctx.error = True
        return buf, cursor

    # Find existing // Tags: line or insert after last metadata line
    tags_line_idx: int | None = None
    last_meta_idx: int | None = None
    existing_tags: set[str] = set()

    for i in range(buf.line_count()):
        bl = buf.get_line(i)
        if bl.line_type == LineType.METADATA:
            last_meta_idx = i
            if bl.text.strip().startswith("// Tags:"):
                tags_line_idx = i
                raw = bl.text.split(":", 1)[1] if ":" in bl.text else ""
                existing_tags = {t.strip().lower() for t in raw.split(",") if t.strip()}

    new_tags = existing_tags | set(names)
    tags_text = f"// Tags: {', '.join(sorted(new_tags))}"

    if tags_line_idx is not None:
        buf = buf.set_line(tags_line_idx, tags_text)
    elif last_meta_idx is not None:
        buf = buf.insert_line(last_meta_idx + 1, tags_text)
    else:
        buf = buf.insert_line(0, tags_text)

    tag_str = " ".join(f"#{n}" for n in names)
    ctx.message = f"Deck tagged: {tag_str}"
    ctx.modified = True
    return buf, cursor


def cmd_duntag(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:duntag name — remove deck-level tags."""
    names, err = _validate_tag_names(cmd.args)
    if err:
        ctx.message = err
        ctx.error = True
        return buf, cursor

    for i in range(buf.line_count()):
        bl = buf.get_line(i)
        if bl.line_type == LineType.METADATA and bl.text.strip().startswith("// Tags:"):
            raw = bl.text.split(":", 1)[1] if ":" in bl.text else ""
            existing = {t.strip().lower() for t in raw.split(",") if t.strip()}
            remaining = existing - set(names)
            if remaining:
                buf = buf.set_line(i, f"// Tags: {', '.join(sorted(remaining))}")
            else:
                buf, _ = buf.delete_lines(i, i)
            ctx.message = f"Removed deck tag(s): {' '.join(f'#{n}' for n in names)}"
            ctx.modified = True
            return buf, cursor

    ctx.message = "No deck tags found"
    return buf, cursor


def cmd_filter(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:filter expr — set tag filter. :filter! — clear filter."""
    if cmd.bang:
        ctx.message = "Filter cleared"
        # Store filter state on context for the TUI to pick up
        if not hasattr(ctx, "_tag_filter"):
            object.__setattr__(ctx, "_tag_filter", None)
        ctx._tag_filter = None  # type: ignore[attr-defined]
        return buf, cursor

    expr = cmd.args.strip()
    if not expr:
        ctx.message = "Usage: :filter <tag-expression>"
        ctx.error = True
        return buf, cursor

    tag_filter = parse_tag_filter(expr)
    # Count how many cards match
    visible = 0
    total = 0
    for line in range(buf.line_count()):
        if buf.is_card_line(line):
            total += 1
            tags = buf.tags_at(line)
            if matches_filter(tags, tag_filter):
                visible += 1

    ctx.message = f"Filter active: {visible}/{total} cards visible"
    ctx._tag_filter = tag_filter  # type: ignore[attr-defined]
    return buf, cursor


def cmd_retag(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:retag /old/new/ — rename a tag across the entire deck."""
    args = cmd.args.strip()
    if not args or args[0] != "/":
        ctx.message = "Usage: :retag /old-tag/new-tag/"
        ctx.error = True
        return buf, cursor

    parts = args[1:].rstrip("/").split("/")
    if len(parts) != 2:
        ctx.message = "Usage: :retag /old-tag/new-tag/"
        ctx.error = True
        return buf, cursor

    old_tag = parts[0].lower()
    new_tag = parts[1].lower()

    if not _TAG_NAME_RE.match(old_tag) or not _TAG_NAME_RE.match(new_tag):
        ctx.message = "Invalid tag name"
        ctx.error = True
        return buf, cursor

    count = 0
    for line in range(buf.line_count()):
        tags = buf.tags_at(line)
        if old_tag in tags:
            new_tags = (tags - {old_tag}) | {new_tag}
            buf = buf.set_tags(line, new_tags)
            count += 1

    if count == 0:
        ctx.message = f"No cards with tag #{old_tag}"
    else:
        ctx.message = f"Renamed #{old_tag} → #{new_tag} on {count} card(s)"
        ctx.modified = True
    return buf, cursor


def register_tag_commands(registry: CommandRegistry) -> None:
    """Register all tag-related ex commands."""
    registry.register("tag", cmd_tag)
    registry.register("untag", cmd_untag)
    registry.register("tags", cmd_tags)
    registry.register("dtag", cmd_dtag)
    registry.register("duntag", cmd_duntag)
    registry.register("filter", cmd_filter)
    registry.register("retag", cmd_retag)

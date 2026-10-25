"""Deck tag commands (:dtag, :duntag) and the :filter view filter.

TUI-agnostic: zero Textual imports.
"""

from __future__ import annotations

from vimtg.domain.tags import (
    TAG_NAME_RE as _TAG_NAME_RE,
)
from vimtg.domain.tags import (
    matches_filter,
    parse_tag_filter,
)
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    ParsedCommand,
)
from vimtg.editor.cursor import Cursor


def _validate_tag_names(raw: str) -> tuple[list[str], str | None]:
    """Parse and validate space-separated tag names. Returns (tags, error)."""
    names = [n.lstrip("#").lower() for n in raw.split() if n.lstrip("#")]
    if not names:
        return [], "No tag name provided"
    for name in names:
        if not _TAG_NAME_RE.match(name):
            return [], f"Invalid tag: '{name}' (letters, digits, hyphens; 1-32 chars)"
    return names, None


def cmd_dtag(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:dtag name [name2...] — add deck-level tags via // Tags: metadata."""
    names, err = _validate_tag_names(cmd.args)
    if err:
        ctx.fail(err)
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
        ctx.fail(err)
        return buf, cursor

    for i in range(buf.line_count()):
        bl = buf.get_line(i)
        if bl.line_type == LineType.METADATA and bl.text.strip().startswith("// Tags:"):
            raw = bl.text.split(":", 1)[1] if ":" in bl.text else ""
            existing = {t.strip().lower() for t in raw.split(",") if t.strip()}
            if not existing & set(names):
                ctx.message = "No such deck tag: " + " ".join(f"#{n}" for n in names)
                return buf, cursor
            remaining = existing - set(names)
            if remaining:
                buf = buf.set_line(i, f"// Tags: {', '.join(sorted(remaining))}")
            else:
                # Keep the empty scaffold line — decks always carry
                # // Tags: so `i` can refill it
                buf = buf.set_line(i, "// Tags:")
            ctx.message = f"Removed deck tag(s): {' '.join(f'#{n}' for n in names)}"
            ctx.modified = True
            return buf, cursor

    ctx.message = "No deck tags found"
    return buf, cursor


def cmd_filter(
    buf: Buffer, cursor: Cursor, cmd: ParsedCommand, ctx: EditorContext,
) -> tuple[Buffer, Cursor]:
    """:filter expr — set tag filter. :filter! or bare :filter — clear."""
    expr = cmd.args.strip()
    if cmd.bang or not expr:
        ctx.message = "Filter cleared"
        ctx.tag_filter = None
        ctx.tag_filter_set = True
        return buf, cursor

    tag_filter = parse_tag_filter(expr)
    visible, total = count_filter_matches(buf, tag_filter)
    ctx.message = filter_status_message(visible, total)
    ctx.tag_filter = tag_filter
    ctx.tag_filter_set = True
    return buf, cursor


def count_filter_matches(buf: Buffer, tag_filter: object) -> tuple[int, int]:
    """Return (matching, total) card-line counts for a tag filter."""
    visible = 0
    total = 0
    for line in range(buf.line_count()):
        if buf.is_card_line(line):
            total += 1
            if matches_filter(buf.tags_at(line), tag_filter):  # type: ignore[arg-type]
                visible += 1
    return visible, total


def filter_status_message(visible: int, total: int) -> str:
    """One consistent wording for the tf / :filter status message."""
    return f"Filter: {visible}/{total} cards match (:filter! clears)"


def register_tag_commands(registry: CommandRegistry) -> None:
    """Register the deck-tag and filter ex commands."""
    registry.register("dtag", cmd_dtag)
    registry.register("duntag", cmd_duntag)
    registry.register("filter", cmd_filter)

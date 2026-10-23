"""Range-based tag mutations shared by :tag/:untag and the t-key input.

The ex commands and the tf/ta/tr/tt key flow previously each carried
their own copy of these loops.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from collections.abc import Iterable

from vimtg.domain.deck_lines import match_metadata
from vimtg.domain.tags import format_tag_summary
from vimtg.editor.buffer import Buffer


def deck_tags(buf: Buffer) -> tuple[str, ...]:
    """The deck-level tags of the '// Tags:' metadata line (set by :dtag)."""
    for i in range(buf.line_count()):
        meta = match_metadata(buf.get_line(i).text)
        if meta is not None and meta[0].lower() == "tags":
            return tuple(t.strip() for t in meta[1].split(",") if t.strip())
    return ()


def tag_summary(buf: Buffer) -> str:
    """The `tl` / `:tags` one-line summary: card tags with counts, or
    the deck's own tags when no card has one."""
    return format_tag_summary(buf.tag_counts(), deck_tags(buf))


def add_tags_in_range(
    buf: Buffer, start: int, end: int, names: Iterable[str]
) -> tuple[Buffer, int]:
    """Add tags to every card line in range. Returns (buffer, cards touched)."""
    count = 0
    for line in range(start, end + 1):
        if buf.is_card_line(line):
            for name in names:
                buf = buf.add_tag(line, name)
            count += 1
    return buf, count


def remove_tags_in_range(
    buf: Buffer, start: int, end: int, names: Iterable[str]
) -> tuple[Buffer, int]:
    """Remove tags from card lines in range. Returns (buffer, tags removed)."""
    count = 0
    for line in range(start, end + 1):
        if buf.is_card_line(line):
            for name in names:
                if name in buf.tags_at(line):
                    buf = buf.remove_tag(line, name)
                    count += 1
    return buf, count


def clear_tags_in_range(buf: Buffer, start: int, end: int) -> tuple[Buffer, int]:
    """Clear all tags from card lines in range. Returns (buffer, cards cleared)."""
    count = 0
    for line in range(start, end + 1):
        if buf.is_card_line(line) and buf.tags_at(line):
            buf = buf.set_tags(line, frozenset())
            count += 1
    return buf, count


def toggle_tag_in_range(
    buf: Buffer, start: int, end: int, tag: str
) -> tuple[Buffer, int, int]:
    """Toggle a tag on card lines in range. Returns (buffer, added, removed)."""
    added = 0
    removed = 0
    for line in range(start, end + 1):
        if buf.is_card_line(line):
            if tag in buf.tags_at(line):
                buf = buf.remove_tag(line, tag)
                removed += 1
            else:
                buf = buf.add_tag(line, tag)
                added += 1
    return buf, added, removed

"""Immutable text buffer representing a deck file.

Each line is classified by type (card, comment, section header, etc.)
for efficient navigation and editing. All mutations return new Buffer
instances — the original is never modified.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from vimtg.domain.categories import (
    format_inline_category,
    parse_category_header,
    parse_inline_category,
    strip_inline_category,
)
from vimtg.domain.deck_lines import (
    CARD_PATTERN,
    CMD_PATTERN,
    CMP_PATTERN,
    MB_PATTERN,
    PLAN_TAG,
    SB_PATTERN,
    apply_zone_effect,
    clamp_quantity,
    format_inline_comment,
    match_metadata,
    parse_card_suffix,
    parse_plan_entry,
    parse_plan_header,
    parse_zone_header,
    split_inline_comment,
    zone_block_contexts,
    zone_context_at,
    zone_context_effect,
    zone_running_context,
)
from vimtg.domain.tags import format_inline_tags, parse_inline_tags, strip_inline_tags


class LineType(Enum):
    COMMENT = "comment"
    SECTION_HEADER = "section"
    CARD_ENTRY = "card"
    SIDEBOARD_ENTRY = "sideboard"
    MAYBEBOARD_ENTRY = "maybeboard"
    COMMANDER_ENTRY = "commander"
    COMPANION_ENTRY = "companion"
    BLANK = "blank"
    METADATA = "metadata"
    # Sideboard plans: 'VS: Tron' and its indented '-4 Bolt' / '+3 Moon'
    PLAN_HEADER = "plan_header"
    PLAN_ENTRY = "plan_entry"


SECTION_HEADERS = frozenset({
    "Creatures", "Creature", "Spells", "Lands", "Land", "Sideboard",
    "Enchantments", "Enchantment", "Artifacts", "Artifact",
    "Planeswalkers", "Planeswalker", "Instants", "Instant",
    "Sorceries", "Sorcery", "Mainboard", "Maybeboard",
    "Other", "Commander", "Companion", "Uncategorized",
})

_CARD_PATTERN = CARD_PATTERN
_SB_PATTERN = SB_PATTERN
_MB_PATTERN = MB_PATTERN
_CMD_PATTERN = CMD_PATTERN
_CMP_PATTERN = CMP_PATTERN
# Splits a card line into (prefix+leading-ws, quantity, rest) so the quantity
# can be replaced in place without disturbing the prefix, name, or tags.
_QUANTITY_SUB = re.compile(
    r"^(\s*(?:SB:|MB:|CMD:|CMP:)?\s*[+-]?\s*)(\d+)(\s.*)$", re.DOTALL
)


@dataclass(frozen=True)
class BufferLine:
    text: str
    line_type: LineType


def classify_line(text: str) -> LineType:
    """Classify a single line of deck text by its syntactic role."""
    stripped = text.strip()
    if not stripped:
        return LineType.BLANK
    if stripped.startswith("//"):
        if match_metadata(stripped) is not None:
            return LineType.METADATA
        if stripped[2:].strip() in SECTION_HEADERS:
            return LineType.SECTION_HEADER
        # "// @name" — a user-defined category header. The @ marker
        # keeps prose comments from classifying as sections.
        if parse_category_header(stripped) is not None:
            return LineType.SECTION_HEADER
        return LineType.COMMENT
    # "DCK:"/"CMD:"/… — Python-style zone block header (cards sit beneath)
    if parse_zone_header(stripped) is not None:
        return LineType.SECTION_HEADER
    # "VS: Tron" — a sideboard plan block header
    if parse_plan_header(stripped) is not None:
        return LineType.PLAN_HEADER
    if _SB_PATTERN.match(stripped):
        return LineType.SIDEBOARD_ENTRY
    if _MB_PATTERN.match(stripped):
        return LineType.MAYBEBOARD_ENTRY
    if _CMD_PATTERN.match(stripped):
        return LineType.COMMANDER_ENTRY
    if _CMP_PATTERN.match(stripped):
        return LineType.COMPANION_ENTRY
    if _CARD_PATTERN.match(stripped):
        return LineType.CARD_ENTRY
    return LineType.COMMENT


CARD_LINE_TYPES = frozenset({
    LineType.CARD_ENTRY,
    LineType.SIDEBOARD_ENTRY,
    LineType.MAYBEBOARD_ENTRY,
    LineType.COMMANDER_ENTRY,
    LineType.COMPANION_ENTRY,
})
_CARD_LINE_TYPES = CARD_LINE_TYPES

# Lines that carry a leading quantity: deck cards plus plan entries.
# Plan entries are NOT card lines — they never count toward the deck,
# sort, or zone moves — but +/- and the name/comment accessors work.
QUANTITY_LINE_TYPES = CARD_LINE_TYPES | {LineType.PLAN_ENTRY}

_CARD_PATTERNS = (
    _CARD_PATTERN, _SB_PATTERN, _MB_PATTERN, _CMD_PATTERN, _CMP_PATTERN,
)

# Zone-block header tag → the LineType its indented bare card lines get
ZONE_TAG_TYPES: dict[str, LineType] = {
    "DCK": LineType.CARD_ENTRY,
    "CMD": LineType.COMMANDER_ENTRY,
    "CMP": LineType.COMPANION_ENTRY,
    "SB": LineType.SIDEBOARD_ENTRY,
    "MB": LineType.MAYBEBOARD_ENTRY,
}
_ZONE_TAG_TYPES = ZONE_TAG_TYPES

# Text section headers whose cards live in a non-main zone; every other
# header ("// Creatures", "// @ramp", ...) labels mainboard cards.
LABEL_ZONE_TYPES: dict[str, LineType] = {
    "Sideboard": LineType.SIDEBOARD_ENTRY,
    "Maybeboard": LineType.MAYBEBOARD_ENTRY,
    "Commander": LineType.COMMANDER_ENTRY,
    "Companion": LineType.COMPANION_ENTRY,
}


def insertion_zone(buffer: Buffer, row: int) -> LineType:
    """The zone a card inserted at `row` should join, cursor-style.

    Priority: the enclosing zone block's running context, then the zone
    of the nearest content line above (a zone card line, or a labeled
    zone header like '// Sideboard'). Blanks and comments are looked
    through; metadata, type/category headers, and the top of the file
    mean mainboard.
    """
    texts = [bl.text for bl in buffer.get_lines()]
    if texts:
        tag = zone_running_context(texts, min(row, len(texts) - 1))
        if tag == PLAN_TAG:
            return LineType.PLAN_ENTRY
        if tag is not None:
            return _ZONE_TAG_TYPES[tag]
    for i in range(min(row, buffer.line_count()) - 1, -1, -1):
        bl = buffer.get_line(i)
        if bl.line_type in (LineType.BLANK, LineType.COMMENT):
            continue
        if bl.line_type in CARD_LINE_TYPES:
            return bl.line_type
        if bl.line_type == LineType.SECTION_HEADER:
            header_tag = parse_zone_header(bl.text)
            if header_tag is not None:
                return _ZONE_TAG_TYPES[header_tag]
            label = bl.text.strip().removeprefix("//").strip()
            return LABEL_ZONE_TYPES.get(label, LineType.CARD_ENTRY)
        return LineType.CARD_ENTRY  # metadata / top of file
    return LineType.CARD_ENTRY


def _classify_in_block(text: str, line_type: LineType, tag: str | None) -> LineType:
    """Apply a block context to a per-line classification.

    Inside a zone block a bare card line takes the zone. Inside a plan
    block any card-shaped line — signed ('-4 Bolt', a COMMENT on its
    own) or unsigned ('4 Bolt', a CARD_ENTRY on its own) — is a plan
    entry; it must never count as a mainboard card.
    """
    if tag is None:
        return line_type
    if tag == PLAN_TAG:
        if line_type == LineType.CARD_ENTRY or (
            line_type == LineType.COMMENT and parse_plan_entry(text) is not None
        ):
            return LineType.PLAN_ENTRY
        return line_type
    if line_type == LineType.CARD_ENTRY:
        return _ZONE_TAG_TYPES[tag]
    return line_type


def classify_lines(texts: Sequence[str]) -> tuple[BufferLine, ...]:
    """Classify lines with zone-block context.

    A bare card line indented under a 'CMD:'-style block header takes
    the block's zone; explicit prefixes and every other line type keep
    their per-line classification (see deck_lines.zone_block_contexts).
    """
    contexts = zone_block_contexts(texts)
    lines: list[BufferLine] = []
    for text, ctx in zip(texts, contexts, strict=True):
        line_type = _classify_in_block(text, classify_line(text), ctx)
        lines.append(BufferLine(text=text, line_type=line_type))
    return tuple(lines)


class Buffer:
    """Immutable deck-as-text-buffer. All mutations return a new Buffer."""

    __slots__ = ("_lines",)

    def __init__(self, lines: tuple[BufferLine, ...]) -> None:
        self._lines = lines

    @staticmethod
    def from_text(text: str) -> Buffer:
        """Parse raw deck text into a classified Buffer.

        Empty text yields a single blank line so to_text()'s trailing
        newline round-trips (a 0-line buffer could not honor it).
        """
        raw_lines = text.split("\n")
        if raw_lines and raw_lines[-1] == "":
            raw_lines = raw_lines[:-1]
        if not raw_lines:
            raw_lines = [""]
        return Buffer(classify_lines(raw_lines))

    def to_text(self) -> str:
        """Serialize buffer back to text (with trailing newline)."""
        return "\n".join(line.text for line in self._lines) + "\n"

    def line_count(self) -> int:
        return len(self._lines)

    def get_line(self, n: int) -> BufferLine:
        """Return line n, clamped to the valid range.

        Callers pass cursor rows that can briefly trail a shrinking
        buffer; clamping (like every other accessor's bounds check)
        beats an IndexError mid-render.
        """
        if not self._lines:
            return BufferLine(text="", line_type=LineType.BLANK)
        return self._lines[max(0, min(n, len(self._lines) - 1))]

    def get_lines(self) -> tuple[BufferLine, ...]:
        return self._lines

    def _texts(self) -> list[str]:
        return [bl.text for bl in self._lines]

    @staticmethod
    def _classify_one(texts: Sequence[str], n: int) -> BufferLine:
        """Classify one row with its zone-block context."""
        text = texts[n]
        line_type = _classify_in_block(
            text, classify_line(text), zone_context_at(texts, n)
        )
        return BufferLine(text=text, line_type=line_type)

    def set_line(self, n: int, text: str) -> Buffer:
        """Return new Buffer with line n replaced.

        An edit can open or close a zone block, changing the zone of the
        indented lines beneath it; only such edits pay for a full
        reclassification. Edits that leave the outgoing block context
        unchanged (the common case) reclassify one row.
        """
        texts = self._texts()
        old_text = texts[n]
        texts[n] = text
        incoming = zone_running_context(texts, n)
        out_old = apply_zone_effect(zone_context_effect(old_text), incoming)
        out_new = apply_zone_effect(zone_context_effect(text), incoming)
        if out_old != out_new:
            return Buffer(classify_lines(texts))
        new_lines = list(self._lines)
        new_lines[n] = self._classify_one(texts, n)
        return Buffer(tuple(new_lines))

    def insert_line(self, n: int, text: str) -> Buffer:
        """Return new Buffer with a line inserted at position n."""
        texts = self._texts()
        texts.insert(n, text)
        incoming = zone_running_context(texts, n)
        if apply_zone_effect(zone_context_effect(text), incoming) != incoming:
            return Buffer(classify_lines(texts))
        new_lines = list(self._lines)
        new_lines.insert(n, self._classify_one(texts, n))
        return Buffer(tuple(new_lines))

    def delete_lines(self, start: int, end: int) -> tuple[Buffer, tuple[str, ...]]:
        """Delete lines [start, end] inclusive. Returns (new_buffer, deleted_texts).

        Indices are clamped to the buffer bounds, so an out-of-range start/end
        (e.g. a stale cursor or an over-wide ``:N,Md`` range) never raises.
        """
        count = len(self._lines)
        start = max(0, min(start, count - 1))
        end = max(0, min(end, count - 1))
        if start > end:
            return self, ()
        deleted = tuple(self._lines[i].text for i in range(start, end + 1))
        if len(self._lines) == len(deleted):
            return Buffer((BufferLine(text="", line_type=LineType.BLANK),)), deleted
        incoming = zone_running_context(self._texts(), start)
        outgoing = incoming
        for text in deleted:
            outgoing = apply_zone_effect(zone_context_effect(text), outgoing)
        if outgoing == incoming:
            remaining_lines = self._lines[:start] + self._lines[end + 1:]
            return Buffer(remaining_lines), deleted
        remaining = self._texts()[:start] + self._texts()[end + 1:]
        return Buffer(classify_lines(remaining)), deleted

    def append_line(self, text: str) -> Buffer:
        """Return new Buffer with a line appended at the end."""
        return self.insert_line(self.line_count(), text)

    def card_name_at(self, line: int) -> str | None:
        """Extract card name from a card/sideboard/commander line, or a
        sideboard-plan entry.

        Strips trailing inline tags ('  #core') and the inline comment
        ('  // note') before returning.
        """
        if self.is_plan_entry(line):
            parsed = parse_plan_entry(self._lines[line].text)
            return parse_card_suffix(parsed[2])[0] if parsed else None
        if not self.is_card_line(line):
            return None
        for pattern in _CARD_PATTERNS:
            m = pattern.match(self._lines[line].text.strip())
            if m:
                return parse_card_suffix(m.group(2))[0]
        return None

    def quantity_at(self, line: int) -> int | None:
        """Extract quantity from a card/sideboard/commander line or a
        sideboard-plan entry."""
        if line < 0 or line >= self.line_count():
            return None
        bl = self._lines[line]
        if bl.line_type == LineType.PLAN_ENTRY:
            parsed = parse_plan_entry(bl.text)
            return clamp_quantity(parsed[1]) if parsed else None
        if bl.line_type not in _CARD_LINE_TYPES:
            return None
        for pattern in _CARD_PATTERNS:
            m = pattern.match(bl.text.strip())
            if m:
                return clamp_quantity(int(m.group(1)))
        return None

    def plan_sign_at(self, line: int) -> str | None:
        """'-' / '+' / '' for a sideboard-plan entry; None elsewhere."""
        if not self.is_plan_entry(line):
            return None
        parsed = parse_plan_entry(self._lines[line].text)
        return parsed[0] if parsed else None

    def set_quantity(self, line: int, quantity: int) -> Buffer:
        """Return a new Buffer with the card quantity on `line` replaced.

        Preserves the SB:/CMD: prefix (or a plan entry's +/- sign), the
        exact card name, and any inline tags — only the leading
        quantity number changes.
        """
        if not self.has_quantity(line):
            return self
        text = self._lines[line].text
        m = _QUANTITY_SUB.match(text)
        if m is None:
            return self
        return self.set_line(line, f"{m.group(1)}{quantity}{m.group(3)}")

    def is_card_line(self, line: int) -> bool:
        """Check whether the given line index holds a card entry."""
        if line < 0 or line >= self.line_count():
            return False
        return self._lines[line].line_type in _CARD_LINE_TYPES

    def is_plan_entry(self, line: int) -> bool:
        """Check whether the given line index holds a sideboard-plan entry."""
        if line < 0 or line >= self.line_count():
            return False
        return self._lines[line].line_type == LineType.PLAN_ENTRY

    def has_quantity(self, line: int) -> bool:
        """Card line or plan entry — anything +/- can adjust."""
        return self.is_card_line(line) or self.is_plan_entry(line)

    def next_card_line(self, from_line: int) -> int | None:
        """Find the next card line after from_line, or None."""
        for i in range(from_line + 1, self.line_count()):
            if self.is_card_line(i):
                return i
        return None

    def prev_card_line(self, from_line: int) -> int | None:
        """Find the previous card line before from_line, or None."""
        for i in range(from_line - 1, -1, -1):
            if self.is_card_line(i):
                return i
        return None

    def section_range(self, line: int) -> tuple[int, int] | None:
        """Find start and end of the contiguous card block containing line."""
        if not self.is_card_line(line):
            return None
        start = line
        while start > 0 and self.is_card_line(start - 1):
            start -= 1
        end = line
        while end < self.line_count() - 1 and self.is_card_line(end + 1):
            end += 1
        return (start, end)

    # ── Tag operations ───────────────────────────────────────────────

    def tags_at(self, line: int) -> frozenset[str]:
        """Extract the tag set from a card line. Returns empty set for non-card lines."""
        if not self.is_card_line(line):
            return frozenset()
        # Split the comment off first — '#word' inside a comment is prose.
        # Strip the category so a non-canonical '#tags  @cat' order still
        # leaves a valid trailing tag suffix for parse_inline_tags.
        base, _ = split_inline_comment(self._lines[line].text)
        return parse_inline_tags(strip_inline_category(base))

    def set_tags(self, line: int, tags: frozenset[str]) -> Buffer:
        """Return new Buffer with the tag suffix on line replaced.

        The inline comment (if any) is preserved after the tags.
        """
        if not self.is_card_line(line):
            return self
        base, comment = split_inline_comment(self._lines[line].text)
        new_text = (
            strip_inline_tags(base)
            + format_inline_tags(tags)
            + format_inline_comment(comment)
        )
        return self.set_line(line, new_text)

    def comment_at(self, line: int) -> str:
        """Inline comment on a card or plan line ('' for none / other lines)."""
        if not self.has_quantity(line):
            return ""
        return split_inline_comment(self._lines[line].text)[1]

    def set_comment(self, line: int, comment: str) -> Buffer:
        """Return new Buffer with the inline comment on a card line replaced.

        An empty comment removes the suffix. Lines without a quantity
        (headers, comments, blanks) are unchanged.
        """
        if not self.has_quantity(line):
            return self
        base, _ = split_inline_comment(self._lines[line].text)
        return self.set_line(line, base + format_inline_comment(comment))

    def add_tag(self, line: int, tag: str) -> Buffer:
        """Return new Buffer with tag added to the card at line."""
        existing = self.tags_at(line)
        return self.set_tags(line, existing | {tag.lower()})

    def remove_tag(self, line: int, tag: str) -> Buffer:
        """Return new Buffer with tag removed from the card at line."""
        existing = self.tags_at(line)
        return self.set_tags(line, existing - {tag.lower()})

    # ── Category operations ──────────────────────────────────────────

    def category_at(self, line: int) -> str:
        """Category of a card line ('' for none / non-card lines)."""
        if not self.is_card_line(line):
            return ""
        # Split the comment off first — '@word' inside a comment is prose
        base, _ = split_inline_comment(self._lines[line].text)
        return parse_inline_category(base)

    def set_category(self, line: int, category: str) -> Buffer:
        """Return new Buffer with the card's category replaced.

        An empty category removes the token. Tags and the inline
        comment are preserved in canonical order (name @cat #tags //).
        Non-card lines are unchanged.
        """
        if not self.is_card_line(line):
            return self
        base, comment = split_inline_comment(self._lines[line].text)
        tags = self.tags_at(line)
        # Category first, then tags — stripping in this order also
        # normalizes a non-canonical '#tags  @cat' suffix.
        name_part = strip_inline_tags(strip_inline_category(base)).rstrip()
        new_text = (
            name_part
            + format_inline_category(category.lower() if category else "")
            + format_inline_tags(tags)
            + format_inline_comment(comment)
        )
        return self.set_line(line, new_text)

    def all_categories(self) -> frozenset[str]:
        """Collect all unique categories across card lines."""
        cats: set[str] = set()
        for i in range(self.line_count()):
            cat = self.category_at(i)
            if cat:
                cats.add(cat)
        return frozenset(cats)

    def category_counts(self) -> dict[str, int]:
        """Count how many card lines carry each category."""
        counts: dict[str, int] = {}
        for i in range(self.line_count()):
            cat = self.category_at(i)
            if cat:
                counts[cat] = counts.get(cat, 0) + 1
        return counts

    def all_tags(self) -> frozenset[str]:
        """Collect all unique tags across every card line in the buffer."""
        tags: set[str] = set()
        for i in range(self.line_count()):
            tags.update(self.tags_at(i))
        return frozenset(tags)

    def tag_counts(self) -> dict[str, int]:
        """Count how many card lines carry each tag across the buffer."""
        counts: dict[str, int] = {}
        for i in range(self.line_count()):
            for tag in self.tags_at(i):
                counts[tag] = counts.get(tag, 0) + 1
        return counts

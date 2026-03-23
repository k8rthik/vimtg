"""Immutable text buffer representing a deck file.

Each line is classified by type (card, comment, section header, etc.)
for efficient navigation and editing. All mutations return new Buffer
instances — the original is never modified.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class LineType(Enum):
    COMMENT = "comment"
    SECTION_HEADER = "section"
    CARD_ENTRY = "card"
    SIDEBOARD_ENTRY = "sideboard"
    COMMANDER_ENTRY = "commander"
    BLANK = "blank"
    METADATA = "metadata"


SECTION_HEADERS = frozenset({
    "Creatures", "Spells", "Lands", "Sideboard", "Enchantments",
    "Artifacts", "Planeswalkers", "Instants", "Sorceries", "Mainboard",
    "Other", "Commander", "Companion",
})

METADATA_KEYS = frozenset({"Deck", "Format", "Author", "Description"})

_CARD_PATTERN = re.compile(r"^\s*(\d+)\s+(.+)$")
_SB_PATTERN = re.compile(r"^SB:\s*(\d+)\s+(.+)$")
_CMD_PATTERN = re.compile(r"^CMD:\s*(\d+)\s+(.+)$")


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
        content = stripped[2:].strip()
        if ":" in content:
            key = content.split(":")[0].strip()
            if key in METADATA_KEYS:
                return LineType.METADATA
        if content in SECTION_HEADERS:
            return LineType.SECTION_HEADER
        return LineType.COMMENT
    if _SB_PATTERN.match(stripped):
        return LineType.SIDEBOARD_ENTRY
    if _CMD_PATTERN.match(stripped):
        return LineType.COMMANDER_ENTRY
    if _CARD_PATTERN.match(stripped):
        return LineType.CARD_ENTRY
    return LineType.COMMENT


_CARD_LINE_TYPES = frozenset({
    LineType.CARD_ENTRY,
    LineType.SIDEBOARD_ENTRY,
    LineType.COMMANDER_ENTRY,
})

_CARD_PATTERNS = (_CARD_PATTERN, _SB_PATTERN, _CMD_PATTERN)


class Buffer:
    """Immutable deck-as-text-buffer. All mutations return a new Buffer."""

    __slots__ = ("_lines",)

    def __init__(self, lines: tuple[BufferLine, ...]) -> None:
        self._lines = lines

    @staticmethod
    def from_text(text: str) -> Buffer:
        """Parse raw deck text into a classified Buffer."""
        raw_lines = text.split("\n")
        if raw_lines and raw_lines[-1] == "":
            raw_lines = raw_lines[:-1]
        return Buffer(
            tuple(
                BufferLine(text=line, line_type=classify_line(line))
                for line in raw_lines
            )
        )

    def to_text(self) -> str:
        """Serialize buffer back to text (with trailing newline)."""
        return "\n".join(line.text for line in self._lines) + "\n"

    def line_count(self) -> int:
        return len(self._lines)

    def get_line(self, n: int) -> BufferLine:
        return self._lines[n]

    def get_lines(self) -> tuple[BufferLine, ...]:
        return self._lines

    def set_line(self, n: int, text: str) -> Buffer:
        """Return new Buffer with line n replaced."""
        new_lines = list(self._lines)
        new_lines[n] = BufferLine(text=text, line_type=classify_line(text))
        return Buffer(tuple(new_lines))

    def insert_line(self, n: int, text: str) -> Buffer:
        """Return new Buffer with a line inserted at position n."""
        new_lines = list(self._lines)
        new_lines.insert(n, BufferLine(text=text, line_type=classify_line(text)))
        return Buffer(tuple(new_lines))

    def delete_lines(self, start: int, end: int) -> tuple[Buffer, tuple[str, ...]]:
        """Delete lines [start, end] inclusive. Returns (new_buffer, deleted_texts)."""
        deleted = tuple(self._lines[i].text for i in range(start, end + 1))
        remaining = list(self._lines[:start]) + list(self._lines[end + 1:])
        if not remaining:
            remaining = [BufferLine(text="", line_type=LineType.BLANK)]
        return Buffer(tuple(remaining)), deleted

    def append_line(self, text: str) -> Buffer:
        """Return new Buffer with a line appended at the end."""
        return self.insert_line(self.line_count(), text)

    def card_name_at(self, line: int) -> str | None:
        """Extract card name from a card/sideboard/commander line."""
        if line < 0 or line >= self.line_count():
            return None
        bl = self._lines[line]
        if bl.line_type == LineType.CARD_ENTRY:
            m = _CARD_PATTERN.match(bl.text.strip())
            return m.group(2) if m else None
        if bl.line_type == LineType.SIDEBOARD_ENTRY:
            m = _SB_PATTERN.match(bl.text.strip())
            return m.group(2) if m else None
        if bl.line_type == LineType.COMMANDER_ENTRY:
            m = _CMD_PATTERN.match(bl.text.strip())
            return m.group(2) if m else None
        return None

    def quantity_at(self, line: int) -> int | None:
        """Extract quantity from a card/sideboard/commander line."""
        if line < 0 or line >= self.line_count():
            return None
        bl = self._lines[line]
        if bl.line_type not in _CARD_LINE_TYPES:
            return None
        for pattern in _CARD_PATTERNS:
            m = pattern.match(bl.text.strip())
            if m:
                return int(m.group(1))
        return None

    def is_card_line(self, line: int) -> bool:
        """Check whether the given line index holds a card entry."""
        if line < 0 or line >= self.line_count():
            return False
        return self._lines[line].line_type in _CARD_LINE_TYPES

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

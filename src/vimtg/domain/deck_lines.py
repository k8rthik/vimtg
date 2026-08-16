"""Deck-line text grammar — the single source of truth.

Both the editor buffer (vimtg.editor.buffer) and the deck file parser
(vimtg.data.deck_repository) match deck lines against these patterns.
Keeping them here prevents the two parsers from drifting apart.
"""

from __future__ import annotations

import re

from vimtg.domain.categories import (
    parse_inline_category,
    strip_inline_category,
)
from vimtg.domain.tags import parse_inline_tags, strip_inline_tags

# A deck line is one of:
#   N Card Name            (mainboard)
#   SB: N Card Name        (sideboard)
#   MB: N Card Name        (maybeboard)
#   CMD: N Card Name       (commander)
#   CMP: N Card Name       (companion)
CARD_PATTERN = re.compile(r"^\s*(\d+)\s+(.+)$")
SB_PATTERN = re.compile(r"^SB:\s*(\d+)\s+(.+)$")
MB_PATTERN = re.compile(r"^MB:\s*(\d+)\s+(.+)$")
CMD_PATTERN = re.compile(r"^CMD:\s*(\d+)\s+(.+)$")
CMP_PATTERN = re.compile(r"^CMP:\s*(\d+)\s+(.+)$")

# "DCK:" on a line of its own is a Python-style block header for the
# main deck: the cards beneath it (indented or not) are mainboard, which
# bare card lines already are — the header is a structural label, not a
# per-line prefix like SB:/CMD:.
DCK_HEADER_PATTERN = re.compile(r"^DCK:\s*$", re.IGNORECASE)


def is_deck_header(text: str) -> bool:
    """True for a 'DCK:' main-deck block header line."""
    return DCK_HEADER_PATTERN.match(text.strip()) is not None

METADATA_KEYS = frozenset(
    {"Deck", "Format", "Author", "Description", "Source", "Tags"}
)
METADATA_PATTERN = re.compile(
    r"^//\s*(" + "|".join(sorted(METADATA_KEYS)) + r")\s*:\s*(.*)$"
)

# Same shape as METADATA_PATTERN, but group 1 captures the full
# "// Key: " prefix (verbatim) so line editing can lock it.
_METADATA_PREFIX_PATTERN = re.compile(
    r"^(\s*//\s*(?:" + "|".join(sorted(METADATA_KEYS)) + r")\s*:\s*)(.*)$"
)

# Inline card comment: "N Card Name  #tags  // comment". The two-space
# delimiter mirrors the tag suffix and keeps canonical double-faced
# names ("Fire // Ice", single spaces) out of comment territory.
COMMENT_DELIMITER = "  //"


def match_metadata(text: str) -> tuple[str, str] | None:
    """Return (key, value) for a '// Key: value' line, else None.

    Value may be '' — empty metadata values are legal so scaffold
    lines like '// Format:' round-trip.
    """
    m = METADATA_PATTERN.match(text.strip())
    if not m:
        return None
    return m.group(1), m.group(2).strip()


def split_metadata_prefix(text: str) -> tuple[str, str] | None:
    """Split a metadata line into (locked '// Key: ' prefix, editable value).

    The prefix is taken verbatim from the line; when it lacks a trailing
    space (empty value, '// Format:'), one is appended so typed values
    land as '// Format: x'. Returns None for non-metadata lines.
    """
    m = _METADATA_PREFIX_PATTERN.match(text)
    if not m:
        return None
    prefix = m.group(1)
    if not prefix.endswith(" "):
        prefix += " "
    return prefix, m.group(2).strip()


def split_inline_comment(text: str) -> tuple[str, str]:
    """Split 'base  // comment' into (base, comment); ('' when none).

    Splits on the FIRST two-space '//' occurrence.
    """
    idx = text.find(COMMENT_DELIMITER)
    if idx == -1:
        return text, ""
    comment = text[idx + len(COMMENT_DELIMITER):].strip()
    return text[:idx].rstrip(), comment


def format_inline_comment(comment: str) -> str:
    """Render a comment as an inline suffix: '  // text' ('' when empty)."""
    comment = comment.strip()
    return f"  // {comment}" if comment else ""


def parse_card_parts(
    raw_name: str,
) -> tuple[str, str, frozenset[str], str]:
    """Decompose a card line's name portion into (name, category, tags, comment).

    Canonical order on a line is 'Name  @category  #tags  // comment'.
    The comment is split off first — '#word' or '@word' inside a
    comment is prose, not a token. The category is stripped before the
    tags so a non-canonical '#tags  @category' order still parses.
    """
    base, comment = split_inline_comment(raw_name)
    category = parse_inline_category(base)
    base = strip_inline_category(base)
    tags = parse_inline_tags(base)
    name = strip_inline_tags(base).strip()
    return name, category, tags, comment


def parse_card_suffix(raw_name: str) -> tuple[str, frozenset[str], str]:
    """Decompose a card line's name portion into (name, tags, comment).

    Convenience wrapper around parse_card_parts for callers that do not
    need the category (the name still has any '@category' stripped).
    """
    name, _, tags, comment = parse_card_parts(raw_name)
    return name, tags, comment

# Sanity bound on parsed quantities: a hand-typed extra digit (or a
# hostile file) must not make stats/diff allocate per-copy work for
# a billion cards.
MAX_QUANTITY = 999


def clamp_quantity(quantity: int) -> int:
    """Cap a parsed quantity at MAX_QUANTITY.

    Only the upper bound is clamped — a parsed 0 is preserved so
    deck validation can still report it as invalid.
    """
    return min(quantity, MAX_QUANTITY)

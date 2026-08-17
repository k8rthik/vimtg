"""Deck-line text grammar — the single source of truth.

Both the editor buffer (vimtg.editor.buffer) and the deck file parser
(vimtg.data.deck_repository) match deck lines against these patterns.
Keeping them here prevents the two parsers from drifting apart.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

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

# A zone name alone on a line is a Python-style block header: the
# indented card lines beneath it belong to that zone. "DCK:" labels the
# main deck (which has no per-line prefix); the others mirror their
# prefixes, so a commander (or partner pair) can be written as
#   CMD:
#       1 Thrasios, Triton Hero
#       1 Tymna the Weaver
ZONE_HEADER_PATTERN = re.compile(r"^(DCK|CMD|CMP|SB|MB):\s*$", re.IGNORECASE)


def parse_zone_header(text: str) -> str | None:
    """Canonical zone tag ('DCK', 'CMD', …) for a bare header line, else None."""
    m = ZONE_HEADER_PATTERN.match(text.strip())
    return m.group(1).upper() if m else None


def is_deck_header(text: str) -> bool:
    """True for a 'DCK:' main-deck block header line."""
    return parse_zone_header(text) == "DCK"


def zone_block_contexts(raw_lines: Sequence[str]) -> list[str | None]:
    """Per-line enclosing zone-block tag, or None outside any block.

    Python-style rules: a bare 'ZONE:' header opens a block; indented
    lines are inside it; blank lines are neutral; any unindented
    non-blank line closes it. Header and blank lines themselves map to
    None. Zone membership applies only to bare card lines — an explicit
    'SB: 1 X' prefix always wins over the enclosing block.
    """
    contexts: list[str | None] = []
    current: str | None = None
    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped:
            contexts.append(None)
            continue
        tag = parse_zone_header(raw)
        if tag is not None:
            current = tag
            contexts.append(None)
            continue
        if raw[:1].isspace():
            contexts.append(current)
            continue
        current = None
        contexts.append(None)
    return contexts


def zone_running_context(raw_lines: Sequence[str], row: int) -> str | None:
    """The zone-block state entering `row`: the open block's tag, or None."""
    current: str | None = None
    for raw in raw_lines[:row]:
        current = apply_zone_effect(zone_context_effect(raw), current)
    return current


def zone_context_at(raw_lines: Sequence[str], row: int) -> str | None:
    """zone_block_contexts(raw_lines)[row], scanning only up to `row`."""
    raw = raw_lines[row]
    if not raw.strip() or parse_zone_header(raw) is not None:
        return None
    if not raw[:1].isspace():
        return None
    return zone_running_context(raw_lines, row)


def zone_context_effect(text: str) -> str:
    """How a line changes the running zone-block context for the lines
    after it: 'set:<TAG>' (a block header), 'clear' (unindented
    non-blank), or 'keep' (blank or indented)."""
    stripped = text.strip()
    if not stripped:
        return "keep"
    tag = parse_zone_header(text)
    if tag is not None:
        return f"set:{tag}"
    return "keep" if text[:1].isspace() else "clear"


def apply_zone_effect(effect: str, incoming: str | None) -> str | None:
    """The zone-block state after a line with `effect`, given the state
    entering it. Lets editors decide whether an edit can change the
    context of any following line."""
    if effect == "keep":
        return incoming
    if effect == "clear":
        return None
    return effect.removeprefix("set:")

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

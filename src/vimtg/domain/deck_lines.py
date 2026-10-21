"""Deck-line text grammar — the single source of truth.

Both the editor buffer (vimtg.editor.buffer) and the deck file parser
(vimtg.data.deck_repository) match deck lines against these patterns.
Keeping them here prevents the two parsers from drifting apart.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

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

# A sideboard plan is a named block: "VS: Tron" followed by indented
# signed entries — "-4 Lightning Bolt" (out of the mainboard) and
# "+3 Alpine Moon" (in from the sideboard). The header may carry a
# "  // note"; the name is whatever precedes it.
PLAN_TAG = "VS"
PLAN_HEADER_PATTERN = re.compile(r"^VS:\s*(.*)$", re.IGNORECASE)
# Sign is optional so an unsigned line inside a plan block still parses
# (and can be flagged) rather than silently becoming a mainboard card.
PLAN_ENTRY_PATTERN = re.compile(r"^\s*([+-]?)\s*(\d+)\s+(.+)$")

# A hand-typed (or MTGO-pasted) bare "Sideboard" line: every unprefixed
# card line after it, indented or not, is a sideboard card, as in
# MTGO/Arena text lists. Zone and plan blocks still take precedence
# for the lines inside them.
_MTGO_SIDEBOARD_HEADER_PATTERN = re.compile(r"^sideboard\s*:?$", re.IGNORECASE)


def parse_zone_header(text: str) -> str | None:
    """Canonical zone tag ('DCK', 'CMD', …) for a bare header line, else None."""
    m = ZONE_HEADER_PATTERN.match(text.strip())
    return m.group(1).upper() if m else None


def parse_plan_header_parts(text: str) -> tuple[str, str] | None:
    """(name, note) for a 'VS: name  // note' plan header, else None.

    A bare 'VS:' with no name is not a header.
    """
    m = PLAN_HEADER_PATTERN.match(text.strip())
    if not m:
        return None
    name, note = split_inline_comment(m.group(1))
    name = name.strip()
    return (name, note) if name else None


def parse_plan_header(text: str) -> str | None:
    """The matchup name of a 'VS: name' plan header line, else None."""
    parts = parse_plan_header_parts(text)
    return parts[0] if parts else None


def parse_plan_entry(text: str) -> tuple[str, int, str] | None:
    """(sign, quantity, rest) for a '[+-]N Card …' plan entry, else None.

    `sign` is '+', '-', or '' when the line has none. `rest` is the raw
    name portion (tags/comment still attached — see parse_card_parts).
    """
    matched = _match_plan_entry(text)
    if matched is None:
        return None
    m, rest = matched
    return m.group(1), int(m.group(2)), rest.strip()


def _match_plan_entry(text: str) -> tuple[re.Match[str], str] | None:
    """(match, rest after the quantity) for a plan-entry-shaped line.

    `rest` keeps its leading whitespace: the two-space '  //' delimiter
    must survive so '-1   // note' reads as a comment with no card, not
    as a card named '// note'.
    """
    stripped = text.strip()
    m = PLAN_ENTRY_PATTERN.match(stripped)
    if not m:
        return None
    return m, stripped[m.end(2):]


def block_header_tag(text: str) -> str | None:
    """Tag of the block a bare header line opens: a zone tag, PLAN_TAG
    for a 'VS: name' plan header, or None for any other line."""
    tag = parse_zone_header(text)
    if tag is not None:
        return tag
    if parse_plan_header(text) is not None:
        return PLAN_TAG
    return None


def is_deck_header(text: str) -> bool:
    """True for a 'DCK:' main-deck block header line."""
    return parse_zone_header(text) == "DCK"


def is_mtgo_sideboard_header(text: str) -> bool:
    """True for a bare MTGO-style 'Sideboard' line."""
    return _MTGO_SIDEBOARD_HEADER_PATTERN.match(text.strip()) is not None


def _zone_contexts(raw_lines: Sequence[str]) -> Iterator[str | None]:
    """The zone context of each line, in order (see zone_block_contexts)."""
    current: str | None = None
    mtgo_sideboard = False
    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped:
            yield None
            continue
        tag = block_header_tag(raw)
        if tag is not None:
            current = tag
            yield None
            continue
        if is_mtgo_sideboard_header(stripped):
            mtgo_sideboard = True
            current = None
            yield None
            continue
        if raw[:1].isspace() and current is not None:
            yield current
            continue
        current = None
        yield "SB" if mtgo_sideboard else None


def zone_block_contexts(raw_lines: Sequence[str]) -> list[str | None]:
    """Per-line enclosing zone tag, or None outside any zone.

    Zone blocks ('SB:') and sideboard-plan blocks ('VS: Tron', tag
    PLAN_TAG) follow the same rules. A plan header closes any zone block
    and vice versa, so plan entries are never pulled into a zone.

    Python-style rules: a bare 'ZONE:' header opens a block; indented
    lines are inside it; blank lines are neutral; any unindented
    non-blank line closes it. Header and blank lines themselves map to
    None. Zone membership applies only to bare card lines — an explicit
    'SB: 1 X' prefix always wins over the enclosing block.

    A bare MTGO-style 'Sideboard' line puts every later line that is
    not inside a block in the 'SB' context, so a pasted MTGO list reads
    the same in the editor as it does to the deck parser.
    """
    return list(_zone_contexts(raw_lines))


def zone_running_context(raw_lines: Sequence[str], row: int) -> str | None:
    """The zone-block state entering `row`: the open block's tag, or None."""
    current: str | None = None
    for raw in raw_lines[:row]:
        current = apply_zone_effect(zone_context_effect(raw), current)
    return current


def zone_context_at(raw_lines: Sequence[str], row: int) -> str | None:
    """zone_block_contexts(raw_lines)[row], scanning only up to `row`."""
    for i, ctx in enumerate(_zone_contexts(raw_lines[: row + 1])):
        if i == row:
            return ctx
    raise IndexError(row)


def zone_context_effect(text: str) -> str:
    """How a line changes the running zone-block context for the lines
    after it: 'set:<TAG>' (a block header), 'clear' (unindented
    non-blank), or 'keep' (blank or indented)."""
    stripped = text.strip()
    if not stripped:
        return "keep"
    tag = block_header_tag(text)
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

# Printing details other deck sites append after a card name: Arena's
# "(SET) 123", Moxfield's "(PLST) ELD-115" / "(CMM) 400a" and finish
# markers ("*F*" foil, "*E*" etched). They name a printing, not a
# card, so they never belong in vimtg's card name. The set code must
# be 2-6 alphanumerics in one case ("ZEN", "plst") so parenthesised
# name parts ("B.F.M. (Big Furry Monster)", "Hazmat Suit (Used)") are
# left alone.
_FINISH_SUFFIX_RE = re.compile(r"\s+\*[A-Za-z]{1,8}\*\s*$")
_PRINTING_SUFFIX_RE = re.compile(
    r"\s+\((?:[A-Z0-9]{2,6}|[a-z0-9]{2,6})\)(?:\s+[^\s()]+)?\s*$"
)

# A UTF-8 byte-order mark that editors (Notepad, Excel) prepend to text.
BOM = "\ufeff"


def strip_printing_suffix(name: str) -> str:
    """Strip a trailing set/collector/finish suffix from a card name.

    'Goblin Guide (ZEN) 126 *F*' -> 'Goblin Guide'. Names without a
    suffix come back unchanged (apart from surrounding whitespace).
    """
    name = name.strip()
    while True:
        stripped = _FINISH_SUFFIX_RE.sub("", name)
        stripped = _PRINTING_SUFFIX_RE.sub("", stripped)
        if stripped == name:
            return name
        name = stripped.strip()


def strip_bom(text: str) -> str:
    """Drop a leading UTF-8 byte-order mark, if any."""
    return text[1:] if text.startswith(BOM) else text


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


# ---------------------------------------------------------------------
# One parse for every card-shaped line
#
# The editor buffer, the deck file parser, :sort and the layout
# regrouper all need "is this a card line, and what card is it?". They
# once each matched the zone patterns themselves and disagreed on the
# details (a pasted '(ZEN) 126' suffix, a line with tags but no name),
# so a card could be one thing to validation and another to the cursor.
# They now all go through parse_card_line / parse_plan_line.
# ---------------------------------------------------------------------

# Zone tag -> the pattern of its per-line prefix. A bare 'N Card' line
# is the main deck ('DCK') unless an enclosing zone block says otherwise
# (see zone_block_contexts). The prefixed shapes never start with a
# digit and the bare one always does, so the order is immaterial.
ZONE_LINE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("SB", SB_PATTERN),
    ("MB", MB_PATTERN),
    ("CMD", CMD_PATTERN),
    ("CMP", CMP_PATTERN),
    ("DCK", CARD_PATTERN),
)
MAIN_ZONE_TAG = "DCK"


@dataclass(frozen=True)
class CardLine:
    """A parsed 'N Card  @category  #tags  // comment' line.

    `zone` is the tag of the line's own prefix ('SB', 'CMD', …), or
    MAIN_ZONE_TAG for a bare line — the zone block enclosing a bare
    line, if any, is the caller's business. `name` has any pasted
    printing suffix ('(ZEN) 126 *F*') stripped and is never empty.
    """

    zone: str
    quantity: int
    name: str
    category: str = ""
    tags: frozenset[str] = frozenset()
    comment: str = ""


@dataclass(frozen=True)
class PlanLine:
    """A parsed sideboard-plan entry: '[+-]N Card  // note'.

    `sign` is '+', '-', or '' for an unsigned line (which is still an
    entry inside a plan block, so it can be flagged rather than taken
    for a mainboard card). `name` is never empty.
    """

    sign: str
    quantity: int
    name: str
    comment: str = ""


def match_card_line(text: str) -> tuple[str, re.Match[str]] | None:
    """(zone tag, match) for a line of card shape, else None.

    Surrounding whitespace is ignored. The match's group 1 is the
    quantity and group 2 the rest of the line; prefer parse_card_line,
    which also decides whether the rest names a card.
    """
    stripped = text.strip()
    for tag, pattern in ZONE_LINE_PATTERNS:
        m = pattern.match(stripped)
        if m:
            return tag, m
    return None


def parse_card_line(text: str) -> CardLine | None:
    """The card a line holds, or None when it is not a card line.

    A line of card shape whose name is empty once the suffix tokens
    are split off ('3  #tag', '2  // note') is not a card line.
    """
    matched = match_card_line(text)
    if matched is None:
        return None
    tag, m = matched
    # The rest of the line keeps its leading whitespace so the two-space
    # '  //' / '  #' / '  @' delimiters survive: '4   // note' is a
    # comment with no card, not a card named '// note'
    name, category, tags, comment = parse_card_parts(text.strip()[m.end(1):])
    name = strip_printing_suffix(name)
    if not name:
        return None
    return CardLine(
        zone=tag,
        quantity=clamp_quantity(int(m.group(1))),
        name=name,
        category=category,
        tags=tags,
        comment=comment,
    )


def is_bare_card_line(text: str) -> bool:
    """True for an unprefixed card line — one whose zone comes from
    the enclosing block (or the main deck outside any block)."""
    card = parse_card_line(text)
    return card is not None and card.zone == MAIN_ZONE_TAG


def parse_plan_line(text: str) -> PlanLine | None:
    """The sideboard-plan entry a line holds, or None.

    Lines with an explicit zone prefix ('SB: 1 X') are zone cards even
    inside a plan block, never plan entries. As for parse_card_line, a
    line with no card name ('-1 #tag') is not an entry.
    """
    matched = match_card_line(text)
    if matched is not None and matched[0] != MAIN_ZONE_TAG:
        return None
    entry = _match_plan_entry(text)
    if entry is None:
        return None
    m, rest = entry
    name, _category, _tags, comment = parse_card_parts(rest)
    if not name:
        return None
    return PlanLine(
        sign=m.group(1), quantity=clamp_quantity(int(m.group(2))), name=name,
        comment=comment,
    )

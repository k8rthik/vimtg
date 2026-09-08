"""Mainboard card placement — one policy for every way a card enters
the main deck.

Search inserts, EDHREC inserts, and `md` zone moves each used to decide
"where does this card go" on their own, and disagreed: one ignored the
deck's layout, another ignored the card's own category. Now a single
function decides, driven by the deck's layout:

- auto-sort off: the card goes where the user opened the line (or the
  end of the mainboard when there is no such place). In a
  category-grouped deck it takes the category of the section it lands
  in, so a card's token and its header always agree.
- type layout: the card joins its primary type's section, created if
  missing; a card with no known type joins '// Other'.
- category layout: a card that already carries a category joins that
  category's section; a card opened under a category header stays
  there and inherits that category; otherwise it joins
  '// Uncategorized'.

`reconcile_category_sections` is the other half of the same invariant,
run after a category edit: every mainboard card whose token disagrees
with the section it sits in moves to the section its token names.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from vimtg.domain.card_types import primary_type
from vimtg.domain.section_keys import SectionKey, SectionKind
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.layout import LAYOUT_CATEGORY, detect_layout, enclosing_category
from vimtg.editor.operators import zone_insert_row
from vimtg.editor.section_model import parse_sections, section_at
from vimtg.editor.sections import (
    UNCATEGORIZED_KEY,
    matched_indent,
    section_insert_row,
)

_OTHER_KEY = SectionKey(SectionKind.OTHER, "Other")


@dataclass(frozen=True)
class PlacementPolicy:
    """What placement needs to know about the editor and the card."""

    auto_sort: bool
    type_line: str | None = None  # the resolved card's type line, if known


@dataclass(frozen=True)
class Placement:
    """Where a new mainboard line goes. `buffer` already holds any header
    (and separator) lines that had to be created; `lines_added` counts
    them so callers can adjust marks. `category` is the token the new
    line must carry ('' for none)."""

    buffer: Buffer
    row: int
    indent: str
    category: str = ""
    lines_added: int = 0


def type_section_key(type_line: str | None) -> SectionKey:
    """The type section a card belongs to; '// Other' when unknown."""
    ptype = primary_type(type_line) if type_line else None
    return SectionKey(SectionKind.TYPE, ptype) if ptype else _OTHER_KEY


def place_mainboard_card(
    buf: Buffer,
    policy: PlacementPolicy,
    *,
    open_row: int | None = None,
    category: str = "",
) -> Placement:
    """Decide where a new mainboard card line goes.

    `open_row` is where the user opened the line (None when the insert
    has no cursor position — EDHREC, a zone move). `category` is a
    token the card already carries (a moved card keeps its own).
    """
    layout = detect_layout(buf)
    if not policy.auto_sort:
        row = open_row if open_row is not None else zone_insert_row(buf, LineType.CARD_ENTRY)
        inherited = enclosing_category(buf, row) if layout == LAYOUT_CATEGORY else ""
        return Placement(buf, row, matched_indent(buf, row), category or inherited)

    if layout == LAYOUT_CATEGORY:
        if category:
            key = SectionKey(SectionKind.CATEGORY, category)
        elif open_row is not None:
            inherited = enclosing_category(buf, open_row)
            return Placement(buf, open_row, matched_indent(buf, open_row), inherited)
        else:
            key = UNCATEGORIZED_KEY
    else:
        key = type_section_key(policy.type_line)

    before = buf.line_count()
    new_buf, row = section_insert_row(buf, key)
    return Placement(
        new_buf, row, matched_indent(new_buf, row), category,
        lines_added=new_buf.line_count() - before,
    )


# ── Category reconcile ───────────────────────────────────────────────


def reconcile_category_sections(buf: Buffer) -> Buffer:
    """In a category-grouped deck, refile every mainboard card whose
    token disagrees with the category section it sits in. Cards under
    a type header or outside any section are left alone. Returns `buf`
    itself when nothing moved."""
    if detect_layout(buf) != LAYOUT_CATEGORY:
        return buf
    while True:
        row = _first_misfiled_row(buf)
        if row is None:
            return buf
        buf = _refile(buf, row)


def _expected_category(buf: Buffer, row: int) -> str | None:
    """Category a card at `row` must carry to match its section, or None
    when its section makes no such claim."""
    section = section_at(parse_sections(buf), row)
    if section is None or section.zone is not LineType.CARD_ENTRY:
        return None
    if section.key.kind is SectionKind.CATEGORY:
        return section.key.ident
    if section.key == UNCATEGORIZED_KEY:
        return ""
    return None


def _first_misfiled_row(buf: Buffer) -> int | None:
    for row in range(buf.line_count()):
        if buf.get_line(row).line_type is not LineType.CARD_ENTRY:
            continue
        expected = _expected_category(buf, row)
        if expected is not None and buf.category_at(row) != expected:
            return row
    return None


def _refile(buf: Buffer, row: int) -> Buffer:
    """Move the card at `row` into the section its token names."""
    body = buf.get_line(row).text.strip()
    category = buf.category_at(row)
    key = SectionKey(SectionKind.CATEGORY, category) if category else UNCATEGORIZED_KEY
    buf, _ = buf.delete_lines(row, row)
    buf, dest = section_insert_row(buf, key)
    return buf.insert_line(dest, f"{matched_indent(buf, dest)}{body}")

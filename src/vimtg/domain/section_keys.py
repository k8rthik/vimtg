"""Section-header vocabulary — the single identity for every header.

A deck buffer groups cards under header lines: type headers
('// Creatures'), category headers ('// @ramp'), zone labels
('// Sideboard'), Python-style zone blocks ('DCK:'), and a few fixed
labels ('// Other', '// Uncategorized'). Every feature that finds,
counts, creates, or drops a section must agree on which headers are
the SAME section, so that identity lives here as a SectionKey and is
never compared as raw header text ('// Sorcery' and '// Sorceries' are
one key).

Pure text vocabulary — no buffer or line-type dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vimtg.domain.card_types import header_primary_type, type_section_label
from vimtg.domain.categories import (
    UNCATEGORIZED_LABEL,
    format_category_header,
    parse_category_header,
)
from vimtg.domain.deck_lines import parse_zone_header

# Tag of the main-deck zone; type/category/other headers all group
# mainboard cards, so their zone is DCK.
MAIN_ZONE_TAG = "DCK"

# Zone tag → the text label its '// Label' header uses
ZONE_LABELS: dict[str, str] = {
    "CMD": "Commander",
    "CMP": "Companion",
    "SB": "Sideboard",
    "MB": "Maybeboard",
}
_ZONE_TAG_BY_LABEL = {label.lower(): tag for tag, label in ZONE_LABELS.items()}

# Fixed mainboard labels that are not a type or category. Matched
# exactly (case-insensitively) — '// Spells' is a header, '// spells
# feel weak' is prose.
OTHER_LABELS: tuple[str, ...] = ("Other", UNCATEGORIZED_LABEL, "Spells", "Mainboard")
_OTHER_BY_LOWER = {label.lower(): label for label in OTHER_LABELS}

COMMENT_MARK = "//"


class SectionKind(Enum):
    TYPE = "type"            # '// Creatures' — ident is the primary type
    CATEGORY = "category"    # '// @ramp'     — ident is the category name
    ZONE_LABEL = "zone"      # '// Sideboard' — ident is the zone tag
    ZONE_BLOCK = "block"     # 'SB:'          — ident is the zone tag
    OTHER = "other"          # '// Other'     — ident is the exact label


@dataclass(frozen=True)
class SectionKey:
    """Canonical identity of a section header, independent of spelling."""

    kind: SectionKind
    ident: str

    @property
    def label(self) -> str:
        """Header body in canonical form: 'Sorceries', '@ramp', 'Sideboard'."""
        if self.kind is SectionKind.TYPE:
            return type_section_label(self.ident)
        if self.kind is SectionKind.CATEGORY:
            return f"@{self.ident}"
        if self.kind is SectionKind.ZONE_LABEL:
            return ZONE_LABELS[self.ident]
        return self.ident

    @property
    def zone_tag(self) -> str:
        """Zone whose cards this section groups ('DCK' for mainboard kinds)."""
        if self.kind in (SectionKind.ZONE_LABEL, SectionKind.ZONE_BLOCK):
            return self.ident
        return MAIN_ZONE_TAG

    @property
    def is_structural(self) -> bool:
        """Bare zone blocks declare a zone; they are never derived from
        the cards beneath them and never auto-dropped."""
        return self.kind is SectionKind.ZONE_BLOCK

    def header_text(self, indent: str = "") -> str:
        """The header line to write for this key."""
        if self.kind is SectionKind.ZONE_BLOCK:
            return f"{indent}{self.ident}:"
        if self.kind is SectionKind.CATEGORY:
            return f"{indent}{format_category_header(self.ident)}"
        return f"{indent}{COMMENT_MARK} {self.label}"


def header_body(text: str) -> str:
    """'    // Sorceries' -> 'Sorceries' (the text after the comment mark)."""
    stripped = text.strip()
    if stripped.startswith(COMMENT_MARK):
        stripped = stripped[len(COMMENT_MARK):]
    return stripped.strip()


def section_key_for_label(label: str) -> SectionKey:
    """Key for a mainboard section named by `label` in any spelling.

    Type names resolve to their TYPE key; anything else is an OTHER key
    carrying the label verbatim, so callers can always render a header.
    """
    ptype = header_primary_type(label)
    if ptype is not None:
        return SectionKey(SectionKind.TYPE, ptype)
    canonical = _OTHER_BY_LOWER.get(label.strip().lower())
    return SectionKey(SectionKind.OTHER, canonical or label.strip())


def parse_section_key(text: str) -> SectionKey | None:
    """SectionKey for a header line, or None when the line is not one.

    Metadata ('// Deck: x'), prose comments, and card lines are None.
    Type and zone labels match case-insensitively; category headers
    follow the '@name' grammar; zone blocks are bare 'TAG:' lines.
    """
    tag = parse_zone_header(text)
    if tag is not None:
        return SectionKey(SectionKind.ZONE_BLOCK, tag)
    stripped = text.strip()
    if not stripped.startswith(COMMENT_MARK):
        return None
    category = parse_category_header(stripped)
    if category is not None:
        return SectionKey(SectionKind.CATEGORY, category)
    body = header_body(stripped)
    ptype = header_primary_type(body)
    if ptype is not None:
        return SectionKey(SectionKind.TYPE, ptype)
    lowered = body.lower()
    if lowered in _ZONE_TAG_BY_LABEL:
        return SectionKey(SectionKind.ZONE_LABEL, _ZONE_TAG_BY_LABEL[lowered])
    if lowered in _OTHER_BY_LOWER:
        return SectionKey(SectionKind.OTHER, _OTHER_BY_LOWER[lowered])
    return None

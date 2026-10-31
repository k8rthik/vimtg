"""Tag token grammar: the `#tag` suffix on card lines and the deck's
`// Tags:` names.

vimtg reads and writes a card line's #tags unchanged (sorted on write)
so other tools' files round-trip, but no longer edits them; :dtag and
:duntag edit the deck-level tags. Stored as frozenset[str] (lowercase,
deduplicated, unordered).

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import re

# One grammar for tag names — the inline token and standalone
# validation are built from the same body
_TAG_BODY = r"[a-zA-Z][a-zA-Z0-9-]{0,31}"
_TAG_TOKEN = re.compile(rf"#({_TAG_BODY})")
TAG_NAME_RE = re.compile(rf"^{_TAG_BODY}$")


def _tag_suffix_index(text: str) -> int | None:
    """Start index of a valid trailing tag suffix ('  #tag1 #tag2').

    Parsing and stripping MUST agree on what counts as tags: a '#word'
    embedded in the name (or a suffix mixing tags with prose) is not a
    tag suffix — extracting tags there while leaving the text intact
    made parse→serialize append a duplicate suffix on every round-trip.
    """
    stripped = text.lstrip()
    if stripped.startswith("#") and _TAG_TOKEN.sub("", stripped).strip() == "":
        return len(text) - len(stripped)  # the text IS a tag list
    idx = text.find("  #")
    if idx == -1:
        return None
    suffix = text[idx + 2:]
    if _TAG_TOKEN.sub("", suffix).strip() == "":
        return idx
    return None


def parse_inline_tags(text: str) -> frozenset[str]:
    """Extract the #tag tokens of a valid trailing tag suffix."""
    idx = _tag_suffix_index(text)
    if idx is None:
        return frozenset()
    return frozenset(
        m.group(1).lower() for m in _TAG_TOKEN.finditer(text[idx:])
    )


def strip_inline_tags(text: str) -> str:
    """Remove the trailing tag suffix (  #tag1 #tag2) from a line.

    Only strips tags after a two-space delimiter to avoid false positives.
    """
    idx = _tag_suffix_index(text)
    return text if idx is None else text[:idx]


def format_inline_tags(tags: frozenset[str]) -> str:
    """Render tags as an inline suffix: '  #tag1 #tag2' (sorted for stability)."""
    if not tags:
        return ""
    sorted_tags = sorted(tags)
    return "  " + " ".join(f"#{t}" for t in sorted_tags)

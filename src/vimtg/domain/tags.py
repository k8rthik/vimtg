"""Tag domain model — parsing, filtering, and formatting for card/deck tags.

Tags are lightweight annotations: #burn-package, #core, #flex-slot.
Stored as frozenset[str] (lowercase, deduplicated, unordered).

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TAG_TOKEN = re.compile(r"#([a-zA-Z][a-zA-Z0-9-]{0,31})")


@dataclass(frozen=True)
class TagFilter:
    """Compiled tag filter expression.

    include: ALL of these must be present (AND)
    exclude: NONE of these may be present (NOT)
    any_of:  at least ONE must be present (OR)
    """

    include: frozenset[str] = frozenset()
    exclude: frozenset[str] = frozenset()
    any_of: frozenset[str] = frozenset()


def parse_tag_filter(expr: str) -> TagFilter:
    """Parse a filter expression string into a TagFilter.

    Syntax:
        core          → include={core}
        core+flex     → include={core, flex}  (AND)
        core|flex     → any_of={core, flex}   (OR)
        -flex         → exclude={flex}
        core -flex    → include={core}, exclude={flex}
    """
    tokens = expr.split()
    include: set[str] = set()
    exclude: set[str] = set()
    any_of: set[str] = set()

    for token in tokens:
        token = token.lstrip("#")
        if not token:
            continue
        if token.startswith("-"):
            tag = token[1:].lower()
            if tag:
                exclude.add(tag)
        elif "|" in token:
            parts = [p.lower() for p in token.split("|") if p]
            any_of.update(parts)
        elif "+" in token:
            parts = [p.lower() for p in token.split("+") if p]
            include.update(parts)
        else:
            include.add(token.lower())

    return TagFilter(
        include=frozenset(include),
        exclude=frozenset(exclude),
        any_of=frozenset(any_of),
    )


def matches_filter(tags: frozenset[str], filt: TagFilter) -> bool:
    """Check whether a set of tags satisfies a filter."""
    if filt.include and not filt.include.issubset(tags):
        return False
    if filt.exclude and filt.exclude & tags:
        return False
    return not (filt.any_of and not filt.any_of & tags)


def parse_inline_tags(text: str) -> frozenset[str]:
    """Extract #tag tokens from a string, returning lowercase frozenset."""
    return frozenset(m.group(1).lower() for m in _TAG_TOKEN.finditer(text))


def strip_inline_tags(text: str) -> str:
    """Remove the trailing tag suffix (  #tag1 #tag2) from a line.

    Only strips tags after a two-space delimiter to avoid false positives.
    """
    idx = text.find("  #")
    if idx == -1:
        return text
    # Verify everything after the two-space delimiter is valid tags
    suffix = text[idx + 2:]
    if _TAG_TOKEN.sub("", suffix).strip() == "":
        return text[:idx]
    return text


def format_inline_tags(tags: frozenset[str]) -> str:
    """Render tags as an inline suffix: '  #tag1 #tag2' (sorted for stability)."""
    if not tags:
        return ""
    sorted_tags = sorted(tags)
    return "  " + " ".join(f"#{t}" for t in sorted_tags)


def format_tag_summary(counts: dict[str, int]) -> str:
    """Render a tag-count map as a status message, sorted by tag name.

    Returns ``"No tags in deck"`` when the map is empty, otherwise
    ``"Tags: #tag1(2) #tag2(1)"``.
    """
    if not counts:
        return "No tags in deck"
    parts = [f"#{t}({c})" for t, c in sorted(counts.items())]
    return f"Tags: {' '.join(parts)}"

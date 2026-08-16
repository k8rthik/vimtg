"""Category domain model — parsing, formatting, and completion.

A category is a single user-defined purpose label on a card: @ramp,
@draw, @wincon. Unlike tags (a set), each card has at most ONE
category — it drives the category-based deck layout, where cards are
grouped under `// @name` section headers.

Stored inline on the card line, canonical order:
    4 Cultivate  @ramp  #core  // comment

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

import re

# One grammar for category names — same shape as tag names so the two
# suffix tokens stay visually consistent on a line
_CATEGORY_BODY = r"[a-zA-Z][a-zA-Z0-9-]{0,31}"
_CATEGORY_TOKEN = re.compile(rf"@({_CATEGORY_BODY})")
CATEGORY_NAME_RE = re.compile(rf"^{_CATEGORY_BODY}$")

# A category section header line: "// @ramp". The explicit @ marker
# keeps user prose comments ("// tweak mana base") unambiguous.
CATEGORY_HEADER_RE = re.compile(rf"^//\s*@({_CATEGORY_BODY})\s*$")

# An inline category suffix: two-space delimiter + token, mirroring the
# tag suffix grammar. Matched anywhere so non-canonical token order
# (category after tags) still parses.
_INLINE_CATEGORY = re.compile(rf"\s\s@({_CATEGORY_BODY})(?=\s|$)")

# Common deck-building categories offered in completion even before
# they appear in any deck (lowercase, hyphenated, alphabetical).
PRESET_CATEGORIES: tuple[str, ...] = (
    "board-wipe",
    "combo",
    "counterspell",
    "draw",
    "graveyard-hate",
    "lands",
    "lifegain",
    "protection",
    "ramp",
    "recursion",
    "removal",
    "threats",
    "tokens",
    "tutor",
    "utility",
    "wincon",
)

# Group label for cards without a category in the category layout
UNCATEGORIZED_LABEL = "Uncategorized"


def parse_inline_category(text: str) -> str:
    """Extract the category from a line's name portion ('' when none).

    Only tokens after a two-space delimiter count — a lone '@' inside
    prose is not a category. The first token wins when several appear.
    """
    m = _INLINE_CATEGORY.search(text)
    return m.group(1).lower() if m else ""


def strip_inline_category(text: str) -> str:
    """Remove every inline category token (and its delimiter) from text."""
    return _INLINE_CATEGORY.sub("", text).rstrip()


def format_inline_category(category: str) -> str:
    """Render a category as an inline suffix: '  @name' ('' when empty)."""
    return f"  @{category}" if category else ""


def format_category_header(category: str) -> str:
    """Render a category section header line: '// @name'."""
    return f"// @{category}"


def parse_category_header(text: str) -> str | None:
    """Return the category of a '// @name' header line, else None."""
    m = CATEGORY_HEADER_RE.match(text.strip())
    return m.group(1).lower() if m else None


def format_category_summary(counts: dict[str, int]) -> str:
    """Render a category-count map as a status message, sorted by name."""
    if not counts:
        return "No categories in deck"
    parts = [f"@{c}({n})" for c, n in sorted(counts.items())]
    return f"Categories: {' '.join(parts)}"


def completion_candidates(
    deck_counts: dict[str, int],
    history: tuple[str, ...] = (),
    presets: tuple[str, ...] = PRESET_CATEGORIES,
) -> tuple[str, ...]:
    """Build the ordered category-completion pool.

    Deck categories first (most-used first), then cross-deck history
    (most recent first), then presets — deduplicated in that order.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    by_count = sorted(deck_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    for name in [c for c, _ in by_count] + list(history) + list(presets):
        name = name.lower()
        if name not in seen and CATEGORY_NAME_RE.match(name):
            seen.add(name)
            ordered.append(name)
    return tuple(ordered)


def complete_category(prefix: str, candidates: tuple[str, ...]) -> str:
    """First candidate starting with prefix ('' when none or empty prefix)."""
    prefix = prefix.lstrip("@").lower()
    if not prefix:
        return ""
    for name in candidates:
        if name.startswith(prefix):
            return name
    return ""

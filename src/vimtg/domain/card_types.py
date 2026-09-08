"""MTG primary card types and basic lands — the single source of truth.

Ordered by conventional deck-list grouping; sorting, stats, and section
creation all share this order so they can't drift apart.
"""

from __future__ import annotations

PRIMARY_TYPES: tuple[str, ...] = (
    "Creature",
    "Planeswalker",
    "Instant",
    "Sorcery",
    "Enchantment",
    "Artifact",
    "Land",
)

TYPE_ORDER: dict[str, int] = {t: i for i, t in enumerate(PRIMARY_TYPES)}

def is_basic_land(name: str) -> bool:
    """Case-insensitive basic-land check ('forest' is still a Forest)."""
    return name.lower() in _BASIC_LANDS_LOWER


BASIC_LANDS = frozenset({
    "Plains",
    "Island",
    "Swamp",
    "Mountain",
    "Forest",
    "Wastes",
    "Snow-Covered Plains",
    "Snow-Covered Island",
    "Snow-Covered Swamp",
    "Snow-Covered Mountain",
    "Snow-Covered Forest",
})

_BASIC_LANDS_LOWER = frozenset(name.lower() for name in BASIC_LANDS)


# Conventional plural section labels for the type-based layout
SECTION_LABELS: dict[str, str] = {
    "Creature": "Creatures",
    "Planeswalker": "Planeswalkers",
    "Instant": "Instants",
    "Sorcery": "Sorceries",
    "Enchantment": "Enchantments",
    "Artifact": "Artifacts",
    "Land": "Lands",
}


def type_section_label(ptype: str | None) -> str:
    """Plural section label for a primary type ('Other' when unknown)."""
    if ptype is None:
        return "Other"
    return SECTION_LABELS.get(ptype, "Other")


# Every spelling a type-section header may use, lowercased, -> the type.
# Hand-written and imported lists use singular ('// Sorcery') and plural
# ('// Sorceries') interchangeably; both name the same section.
_LABEL_TYPES: dict[str, str] = {
    **{ptype.lower(): ptype for ptype in PRIMARY_TYPES},
    **{label.lower(): ptype for ptype, label in SECTION_LABELS.items()},
}


def header_primary_type(label: str) -> str | None:
    """The primary type a section label names, or None for labels that
    aren't a type ('Other', 'Sideboard', '@ramp', 'Artifact Lands').

    Tolerant of singular/plural and case so 'Sorcery' and 'Sorceries'
    can never be treated as two different sections.
    """
    return _LABEL_TYPES.get(label.strip().lower())


def primary_type(type_line: str) -> str | None:
    """Return the first matching primary type from a card's front face."""
    front = type_line.split("—")[0].split("//")[0].strip()
    for t in PRIMARY_TYPES:
        if t in front:
            return t
    return None

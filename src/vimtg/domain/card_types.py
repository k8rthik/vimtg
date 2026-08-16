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


def primary_type(type_line: str) -> str | None:
    """Return the first matching primary type from a card's front face."""
    front = type_line.split("—")[0].split("//")[0].strip()
    for t in PRIMARY_TYPES:
        if t in front:
            return t
    return None

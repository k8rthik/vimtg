"""Human-readable slug generation for unnamed deck files.

Generates MTG-themed slugs like 'arcane-phoenix-deck' for new decks
that haven't been given an explicit filename.
"""

from __future__ import annotations

import random
from pathlib import Path

_ADJECTIVES = (
    "arcane",
    "blazing",
    "crimson",
    "dire",
    "eldritch",
    "feral",
    "gilded",
    "hidden",
    "infernal",
    "jade",
    "keen",
    "lunar",
    "molten",
    "noble",
    "obsidian",
    "prismatic",
    "radiant",
    "savage",
    "twilight",
    "umbral",
    "verdant",
    "wicked",
    "zealous",
    "ancient",
    "brazen",
    "celestial",
    "dread",
    "ethereal",
    "frozen",
    "grim",
    "hollow",
    "iron",
    "jeweled",
    "mystic",
    "pale",
    "runic",
    "silent",
    "spectral",
    "volatile",
)

_NOUNS = (
    "bolt",
    "phoenix",
    "dragon",
    "storm",
    "blade",
    "lotus",
    "titan",
    "hydra",
    "sphinx",
    "angel",
    "demon",
    "golem",
    "drake",
    "wraith",
    "knight",
    "oracle",
    "falcon",
    "serpent",
    "griffin",
    "lich",
    "rogue",
    "shaman",
    "wurm",
    "elemental",
    "specter",
    "mage",
    "forge",
    "tower",
    "vault",
    "throne",
    "pyre",
    "cairn",
    "nexus",
    "shard",
    "sigil",
    "relic",
    "crypt",
    "grove",
    "bastion",
    "sanctum",
)


def generate_slug() -> str:
    """Generate a random MTG-themed slug like 'arcane-phoenix-deck'."""
    adjective = random.choice(_ADJECTIVES)  # noqa: S311
    noun = random.choice(_NOUNS)  # noqa: S311
    return f"{adjective}-{noun}-deck"


def generate_unique_path(directory: Path, max_attempts: int = 100) -> Path:
    """Generate a slug-based .deck path that doesn't collide with existing files.

    Raises RuntimeError if no unique name found within max_attempts.
    """
    for _ in range(max_attempts):
        slug = generate_slug()
        path = directory / f"{slug}.deck"
        if not path.exists():
            return path
    msg = f"Could not generate unique filename after {max_attempts} attempts"
    raise RuntimeError(msg)

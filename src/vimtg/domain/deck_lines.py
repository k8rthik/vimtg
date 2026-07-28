"""Deck-line text grammar — the single source of truth.

Both the editor buffer (vimtg.editor.buffer) and the deck file parser
(vimtg.data.deck_repository) match deck lines against these patterns.
Keeping them here prevents the two parsers from drifting apart.
"""

from __future__ import annotations

import re

# A deck line is one of:
#   N Card Name            (mainboard)
#   SB: N Card Name        (sideboard)
#   CMD: N Card Name       (commander)
CARD_PATTERN = re.compile(r"^\s*(\d+)\s+(.+)$")
SB_PATTERN = re.compile(r"^SB:\s*(\d+)\s+(.+)$")
CMD_PATTERN = re.compile(r"^CMD:\s*(\d+)\s+(.+)$")

METADATA_KEYS = frozenset({"Deck", "Format", "Author", "Description", "Tags"})
METADATA_PATTERN = re.compile(
    r"^//\s*(" + "|".join(sorted(METADATA_KEYS)) + r"):\s*(.+)$"
)

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

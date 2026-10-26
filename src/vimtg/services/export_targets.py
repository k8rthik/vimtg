"""Export destinations: the one table of where a deck can be exported,
how each destination wants card names written, and what it checks
before a write.

Pure and offline: card data comes in as a name -> Card mapping, never
from the database.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from vimtg.domain.card import Card
from vimtg.domain.deck import Deck


class DeckFormat(Enum):
    """A serializer: the text layout a destination is written in."""

    VIMTG = "vimtg"
    MTGO = "mtgo"
    MTGO_DEK = "dek"  # MTGO's native .dek XML file
    ARENA = "arena"
    MOXFIELD = "moxfield"
    ARCHIDEKT = "archidekt"
    LIST = "list"  # bare 'N Name' lines for MPC Autofill and stores — export only
    GUIDE = "guide"  # sideboard guide as Markdown — export only


def front_face_name(name: str, card: Card | None = None) -> str:
    """The name MTGO and Arena expect for a multi-faced card: the front
    face of a DFC or adventure card ('Brazen Borrower // Petty Theft'
    -> 'Brazen Borrower'). Single-faced names are unchanged.

    Split cards ('Fire // Ice') are listed under both halves by the
    clients, so when `card` says the layout is split the full name is
    kept. Without card data a ' // ' name falls back to its front face.

    SEAM: names are split on the canonical ' // ' only. When the card
    repository grows a front-face resolver (another workstream), route
    unresolved/non-canonical spellings through it here; this function
    must stay free of database access so exports work offline.
    """
    if card is not None and card.layout in _FULL_NAME_LAYOUTS:
        return name
    return name.split(" // ", 1)[0].strip() or name


# Scryfall layouts whose "A // B" name is what MTGO/Arena list
_FULL_NAME_LAYOUTS = frozenset({"split"})


def official_name(name: str, resolved: Mapping[str, Card]) -> str:
    """The resolved card's full official (Scryfall) name; the typed name
    without card data."""
    card = resolved.get(name)
    return card.name if card else name


class Naming(Enum):
    """How a destination writes a card's name."""

    TYPED = "as typed"
    # The full Scryfall name ('Bonecrusher Giant // Stomp'): Moxfield
    # and Archidekt import by it
    OFFICIAL = "full official name"
    # What MTGO and Arena list: the front face of a DFC or adventure
    # card, both halves of a split card ('Fire // Ice')
    CLIENT = "client name"
    # The front face of every multi-faced card, split included: MPC
    # Autofill reads ' // ' as a front/back separator
    FRONT_FACE = "front face"

    def write(self, typed: str, resolved: Mapping[str, Card]) -> str:
        """`typed` (a deck line's name) as this naming writes it."""
        match self:
            case Naming.TYPED:
                return typed
            case Naming.OFFICIAL:
                return official_name(typed, resolved)
            case Naming.CLIENT:
                card = resolved.get(typed)
                return front_face_name(card.name if card else typed, card)
            case Naming.FRONT_FACE:
                return front_face_name(official_name(typed, resolved))


class IssueLevel(Enum):
    ERROR = "error"  # the destination rejects the export: blocks the write
    WARNING = "warning"  # worth knowing; never blocks


@dataclass(frozen=True)
class ExportIssue:
    """One finding of a destination's checks, naming the cards it is about."""

    level: IssueLevel
    message: str
    cards: tuple[str, ...] = ()


# A destination check: the deck about to be exported and its card data
# (None when there is no card database) -> an issue, or None when fine
Check = Callable[[Deck, Mapping[str, Card] | None], ExportIssue | None]


@dataclass(frozen=True)
class ExportTarget:
    """A place a deck is exported to: its name and aliases (for :export,
    :clipboard and `vimtg convert --to`), its serializer, how it writes
    card names, and the checks run before a write."""

    name: str
    aliases: tuple[str, ...]
    fmt: DeckFormat
    naming: Naming
    checks: tuple[Check, ...] = ()


# Every destination, in the order help lists them ('mtga' is Arena
# under its client's name)
TARGETS: tuple[ExportTarget, ...] = (
    ExportTarget("arena", ("mtga",), DeckFormat.ARENA, Naming.CLIENT),
    ExportTarget("mtgo", (), DeckFormat.MTGO, Naming.CLIENT),
    ExportTarget("dek", (), DeckFormat.MTGO_DEK, Naming.CLIENT),
    ExportTarget("moxfield", (), DeckFormat.MOXFIELD, Naming.OFFICIAL),
    ExportTarget("archidekt", (), DeckFormat.ARCHIDEKT, Naming.OFFICIAL),
    ExportTarget("list", (), DeckFormat.LIST, Naming.FRONT_FACE),
    ExportTarget("mpc", (), DeckFormat.LIST, Naming.FRONT_FACE),
    ExportTarget("tcgplayer", (), DeckFormat.LIST, Naming.FRONT_FACE),
    ExportTarget("vimtg", (), DeckFormat.VIMTG, Naming.TYPED),
    ExportTarget("guide", (), DeckFormat.GUIDE, Naming.TYPED),
)

_BY_NAME: Mapping[str, ExportTarget] = MappingProxyType({
    name: t for t in TARGETS for name in (t.name, *t.aliases)
})

# The destination each serializer is written for when only the format
# is named (the first target listed for it)
FORMAT_TARGETS: Mapping[DeckFormat, ExportTarget] = MappingProxyType({
    fmt: next(t for t in TARGETS if t.fmt is fmt) for fmt in DeckFormat
})


def target_named(name: str) -> ExportTarget | None:
    """The destination `name` (any case, aliases included), or None."""
    return _BY_NAME.get(name.lower())


def target_names() -> tuple[str, ...]:
    """Every name a destination answers to, aliases after their target."""
    return tuple(_BY_NAME)

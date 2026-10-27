"""Export destinations: the one table of where a deck can be exported,
how each destination wants card names written, and what it checks
before a write.

Pure and offline: card data comes in as a name -> Card mapping, never
from the database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType

from vimtg.domain.card import Card
from vimtg.domain.card_names import CardMap
from vimtg.domain.deck import Deck, DeckSection


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

    def text(self, named: int | None = 2) -> str:
        """The message with its cards, a list longer than `named` cut to
        that many ('Not on MTG Arena: Goblin Guide, Sol Ring and 3
        more'); None names every card."""
        if not self.cards:
            return self.message
        shown = ", ".join(self.cards[:named])
        rest = len(self.cards) - len(self.cards[:named])
        return f"{self.message}: {shown}" + (f" and {rest} more" if rest > 0 else "")


# A destination check: the deck about to be exported and its card data
# (None when there is no card database) -> an issue, or None when fine
Check = Callable[[Deck, Mapping[str, Card] | None], ExportIssue | None]


# The zones each format writes; the checks see only these
_PLAYED = frozenset({
    DeckSection.COMMANDER, DeckSection.COMPANION, DeckSection.MAIN, DeckSection.SIDEBOARD,
})
_EVERY_ZONE = frozenset(DeckSection)
_WRITTEN_ZONES: Mapping[DeckFormat, frozenset[DeckSection]] = MappingProxyType({
    DeckFormat.VIMTG: _EVERY_ZONE,
    DeckFormat.MTGO: _PLAYED,  # commander and companion park in the sideboard
    DeckFormat.MTGO_DEK: _PLAYED,
    DeckFormat.ARENA: _PLAYED,
    DeckFormat.MOXFIELD: _EVERY_ZONE,
    DeckFormat.ARCHIDEKT: _EVERY_ZONE,
    DeckFormat.LIST: _PLAYED,
    DeckFormat.GUIDE: _EVERY_ZONE,
})


def _unique(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))


def _resolved_cards(deck: Deck, resolved: Mapping[str, Card]) -> tuple[Card, ...]:
    """The deck's cards that card data knows, once each, in deck order."""
    cards = (resolved.get(e.card_name) for e in deck.entries)
    found = {c.name: c for c in cards if c is not None}
    return tuple(found.values())


def _known_names(deck: Deck, resolved: Mapping[str, Card] | None) -> ExportIssue | None:
    """Every destination: names the card database cannot resolve."""
    if resolved is None:
        return ExportIssue(
            IssueLevel.WARNING,
            "No card database, so export checks were limited (run vimtg sync)",
        )
    unknown = _unique(e.card_name for e in deck.entries if e.card_name not in resolved)
    if not unknown:
        return None
    return ExportIssue(
        IssueLevel.WARNING,
        "Not in the card database; the destination may not recognise these",
        unknown,
    )


def _has_cards(deck: Deck, _resolved: Mapping[str, Card] | None) -> ExportIssue | None:
    """Every card-list destination: something to write."""
    if deck.entries:
        return None
    return ExportIssue(IssueLevel.ERROR, "No cards to export")


def _no_at_sign(deck: Deck, resolved: Mapping[str, Card] | None) -> ExportIssue | None:
    """MPC Autofill reads '@' as its image-id separator
    (SelectedImageSeparator in chilli-axe/mpc-autofill)."""
    written = (Naming.FRONT_FACE.write(e.card_name, resolved or {}) for e in deck.entries)
    bad = _unique(n for n in written if "@" in n)
    if not bad:
        return None
    return ExportIssue(
        IssueLevel.ERROR, "MPC Autofill reads '@' as an image-id separator", bad,
    )


def _on_arena(deck: Deck, resolved: Mapping[str, Card] | None) -> ExportIssue | None:
    """MTG Arena: every Arena card is in its Timeless format, so a card
    Timeless lists as not_legal is not on Arena and the import fails.
    Banned and restricted cards are on Arena."""
    cards = _resolved_cards(deck, resolved or {})
    if not cards:
        return None
    if not any(_TIMELESS in c.legalities for c in cards):
        return ExportIssue(IssueLevel.WARNING, "Arena availability unknown; run vimtg sync")
    missing = tuple(c.name for c in cards if c.legalities.get(_TIMELESS) == "not_legal")
    if not missing:
        return None
    return ExportIssue(IssueLevel.ERROR, "Not on MTG Arena, so Arena rejects the import", missing)


_TIMELESS = "timeless"


def _on_mtgo(deck: Deck, resolved: Mapping[str, Card] | None) -> ExportIssue | None:
    """MTGO: a card with no tix price may not be sold there. Basic
    lands have none because MTGO gives them away."""
    cards = _resolved_cards(deck, resolved or {})
    unpriced = tuple(
        c.name for c in cards if c.prices.tix is None and "Basic" not in c.type_line
    )
    if not unpriced:
        return None
    return ExportIssue(IssueLevel.WARNING, "No tix price, so may not be on MTGO", unpriced)


def _has_plans(deck: Deck, _resolved: Mapping[str, Card] | None) -> ExportIssue | None:
    """The sideboard guide: plans to write."""
    if deck.plans:
        return None
    return ExportIssue(IssueLevel.ERROR, "No sideboard plans to export (add a VS: block)")


_GENERIC: tuple[Check, ...] = (_known_names, _has_cards)


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
    # The success message reports how many cards were written
    counts_cards: bool = False

    @property
    def zones(self) -> frozenset[DeckSection]:
        """The deck zones this destination's format writes."""
        return _WRITTEN_ZONES[self.fmt]


# Every destination, in the order help lists them ('mtga' is Arena
# under its client's name)
TARGETS: tuple[ExportTarget, ...] = (
    ExportTarget(
        "arena", ("mtga",), DeckFormat.ARENA, Naming.CLIENT, (*_GENERIC, _on_arena),
    ),
    ExportTarget("mtgo", (), DeckFormat.MTGO, Naming.CLIENT, (*_GENERIC, _on_mtgo)),
    ExportTarget("dek", (), DeckFormat.MTGO_DEK, Naming.CLIENT, (*_GENERIC, _on_mtgo)),
    ExportTarget("moxfield", (), DeckFormat.MOXFIELD, Naming.OFFICIAL, _GENERIC),
    ExportTarget("archidekt", (), DeckFormat.ARCHIDEKT, Naming.OFFICIAL, _GENERIC),
    ExportTarget("list", (), DeckFormat.LIST, Naming.FRONT_FACE, _GENERIC),
    ExportTarget(
        "mpc", (), DeckFormat.LIST, Naming.FRONT_FACE, (*_GENERIC, _no_at_sign),
        counts_cards=True,
    ),
    # TCGplayer's mass entry reads 'qty name [SET] number'; vimtg writes
    # no set, so only the generic checks apply
    ExportTarget("tcgplayer", (), DeckFormat.LIST, Naming.FRONT_FACE, _GENERIC),
    # vimtg is the deck as :w writes it, nothing to check
    ExportTarget("vimtg", (), DeckFormat.VIMTG, Naming.TYPED),
    # A guide is read by people, not imported: only the plans matter
    ExportTarget("guide", (), DeckFormat.GUIDE, Naming.TYPED, (_has_plans,)),
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


def check_export(
    deck: Deck, resolved: Mapping[str, Card] | None, target: ExportTarget,
) -> tuple[ExportIssue, ...]:
    """What `target` finds wrong with exporting `deck`, errors first.
    `resolved` maps deck names to cards; None means there is no card
    database. Only the zones the target writes are checked."""
    written = replace(deck, entries=tuple(e for e in deck.entries if e.section in target.zones))
    lookup = None if resolved is None else CardMap(resolved)
    issues = (check(written, lookup) for check in target.checks)
    found = [i for i in issues if i is not None]
    return tuple(sorted(found, key=lambda i: i.level is not IssueLevel.ERROR))


def exported_card_count(deck: Deck, target: ExportTarget) -> int:
    """How many cards `target` writes for `deck`."""
    return sum(e.quantity for e in deck.entries if e.section in target.zones)

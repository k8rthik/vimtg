"""Deck validation rules — the single implementation.

Used by both the CLI (vimtg validate) and the editor (:validate) so the
two can never disagree about what a legal deck looks like. When a format
is supplied, per-card Scryfall legalities and per-format construction
rules (deck size, copy limit, commander) are checked as well.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vimtg.domain.card_types import is_basic_land
from vimtg.domain.deck import Deck, DeckEntry, DeckSection
from vimtg.domain.formats import FormatRules, get_format_rules

if TYPE_CHECKING:
    from vimtg.domain.card import Card

# Sections whose entries count toward deck size / copy limits.
# Maybeboard is a scratchpad outside the deck proper.
_COUNTED_SECTIONS = (DeckSection.MAIN, DeckSection.SIDEBOARD)

# Sections that count toward per-card copy limits. The commander is part
# of the deck: CMD: Atraxa plus a mainboard Atraxa is two copies.
_COPY_SECTIONS = (
    DeckSection.MAIN, DeckSection.SIDEBOARD, DeckSection.COMMANDER,
)


@dataclass(frozen=True)
class ValidationError:
    level: str  # "error" or "warning"
    message: str
    line_number: int | None = None


def validate_deck(
    deck: Deck,
    resolved: dict[str, Card] | None = None,
    fmt: str = "",
) -> list[ValidationError]:
    """Validate deck structure and (when `fmt` is set) format legality.

    Pass `resolved` (card-name lookups) to also flag unknown names and
    run per-card legality checks; an empty dict means "no card database"
    and skips those checks. `fmt` empty or unknown falls back to the
    generic 60-card constructed rules.
    """
    errors: list[ValidationError] = []
    lookup = _lowercase_lookup(resolved)

    for entry in deck.entries:
        if entry.quantity <= 0:
            errors.append(
                ValidationError(
                    "error",
                    f"Invalid quantity {entry.quantity} for {entry.card_name}",
                    line_number=entry.line_number,
                )
            )

    if lookup:
        for entry in deck.entries:
            if entry.card_name.lower() not in lookup:
                errors.append(
                    ValidationError(
                        "warning",
                        f"Card not found: {entry.card_name}",
                        line_number=entry.line_number,
                    )
                )

    errors.extend(_check_companion(deck, lookup))

    rules = get_format_rules(fmt)
    if rules is None:
        if fmt.strip():
            errors.append(
                ValidationError("warning", f"Unknown format: {fmt}")
            )
        errors.extend(_generic_checks(deck))
        return errors

    errors.extend(_check_legality(deck, lookup, rules))
    errors.extend(_check_copy_limit(deck, rules))
    errors.extend(_check_deck_size(deck, rules))
    errors.extend(_check_sideboard(deck, rules))
    if rules.requires_commander:
        errors.extend(_check_commander(deck, lookup, rules))
    return errors


def _lowercase_lookup(
    resolved: dict[str, Card] | None,
) -> dict[str, Card]:
    """Key resolved cards by lowercase name.

    CardRepository.get_by_names matches COLLATE NOCASE but keys results
    by the DB-canonical name, so a hand-typed 'lightning bolt' must
    still find its Card here.
    """
    if not resolved:
        return {}
    return {name.lower(): card for name, card in resolved.items()}


def _counted_copies(deck: Deck) -> dict[str, int]:
    """Total copies per card name across mainboard, sideboard, commander.

    Keyed by lowercase name: card resolution is case-insensitive, so
    '4 Lightning Bolt' + '4 lightning bolt' is 8 copies of one card,
    not two clean playsets.
    """
    combined: dict[str, int] = {}
    for entry in deck.entries:
        if entry.section in _COPY_SECTIONS:
            key = entry.card_name.lower()
            combined[key] = combined.get(key, 0) + entry.quantity
    return combined


def _display_names(deck: Deck) -> dict[str, str]:
    """First-seen original spelling per lowercase card name, for messages."""
    names: dict[str, str] = {}
    for entry in deck.entries:
        names.setdefault(entry.card_name.lower(), entry.card_name)
    return names


def _generic_checks(deck: Deck) -> list[ValidationError]:
    """Format-agnostic rules: 4-of, 60-card minimum, 15-card sideboard."""
    errors: list[ValidationError] = []

    display = _display_names(deck)
    for name, qty in _counted_copies(deck).items():
        if qty > 4 and not is_basic_land(name):
            errors.append(
                ValidationError(
                    "warning",
                    f"More than 4 copies of {display.get(name, name)}",
                )
            )

    main_count = sum(e.quantity for e in deck.mainboard())
    if main_count == 0:
        errors.append(ValidationError("error", "No mainboard cards"))
    elif main_count < 60:
        errors.append(
            ValidationError(
                "warning", f"Mainboard has {main_count} cards (minimum 60)"
            )
        )

    side_count = sum(e.quantity for e in deck.sideboard())
    if side_count > 15:
        errors.append(
            ValidationError(
                "warning", f"Sideboard has {side_count} cards (maximum 15)"
            )
        )
    return errors


def _check_legality(
    deck: Deck, lookup: dict[str, Card], rules: FormatRules
) -> list[ValidationError]:
    """Flag banned / not-legal / restricted-over-limit cards per entry."""
    if not lookup:
        return []
    errors: list[ValidationError] = []
    copies = _counted_copies(deck)
    for entry in deck.entries:
        card = lookup.get(entry.card_name.lower())
        if card is None or not card.legalities:
            continue
        status = card.legalities.get(rules.name)
        # Maybeboard cards are outside the deck: surface legality as a
        # heads-up warning, never an error.
        level = (
            "warning" if entry.section == DeckSection.MAYBEBOARD else "error"
        )
        if status == "banned":
            errors.append(
                ValidationError(
                    level,
                    f"{entry.card_name} is banned in {rules.name}",
                    line_number=entry.line_number,
                )
            )
        elif status == "not_legal":
            errors.append(
                ValidationError(
                    level,
                    f"{entry.card_name} is not legal in {rules.name}",
                    line_number=entry.line_number,
                )
            )
        elif (
            status == "restricted"
            and entry.section in _COPY_SECTIONS
            and copies.get(entry.card_name.lower(), 0) > 1
        ):
            errors.append(
                ValidationError(
                    "error",
                    f"{entry.card_name} is restricted (max 1 copy)",
                    line_number=entry.line_number,
                )
            )
    return errors


def _check_copy_limit(
    deck: Deck, rules: FormatRules
) -> list[ValidationError]:
    """Flag every entry-line of a card exceeding the format's copy limit."""
    copies = _counted_copies(deck)
    over = {
        name
        for name, qty in copies.items()
        if qty > rules.copy_limit and not is_basic_land(name)
    }
    if not over:
        return []
    limit_word = "copy" if rules.copy_limit == 1 else "copies"
    return [
        ValidationError(
            "error",
            f"{entry.card_name}: {copies[entry.card_name.lower()]} copies "
            f"(max {rules.copy_limit} {limit_word} in {rules.name})",
            line_number=entry.line_number,
        )
        for entry in deck.entries
        if entry.card_name.lower() in over and entry.section in _COPY_SECTIONS
    ]


def _check_deck_size(
    deck: Deck, rules: FormatRules
) -> list[ValidationError]:
    """Exact-size formats get a deck-level error; others a minimum warning."""
    main_count = sum(e.quantity for e in deck.mainboard())
    if rules.exact_deck_size is not None:
        commander_count = sum(
            e.quantity
            for e in deck.entries
            if e.section == DeckSection.COMMANDER
        )
        total = main_count + commander_count
        if total != rules.exact_deck_size:
            return [
                ValidationError(
                    "error",
                    f"Deck has {total} cards "
                    f"({rules.name} requires exactly {rules.exact_deck_size})",
                )
            ]
        return []
    if main_count == 0:
        return [ValidationError("error", "No mainboard cards")]
    if main_count < rules.min_deck_size:
        return [
            ValidationError(
                "warning",
                f"Mainboard has {main_count} cards "
                f"(minimum {rules.min_deck_size})",
            )
        ]
    return []


def _check_sideboard(
    deck: Deck, rules: FormatRules
) -> list[ValidationError]:
    sideboard = deck.sideboard()
    if not rules.allows_sideboard:
        return [
            ValidationError(
                "error",
                f"{rules.name} decks have no sideboard",
                line_number=entry.line_number,
            )
            for entry in sideboard
        ]
    side_count = sum(e.quantity for e in sideboard)
    if side_count > rules.max_sideboard:
        return [
            ValidationError(
                "warning",
                f"Sideboard has {side_count} cards "
                f"(maximum {rules.max_sideboard})",
            )
        ]
    return []


def _check_companion(
    deck: Deck, lookup: dict[str, Card]
) -> list[ValidationError]:
    """Companion zone rules — format-agnostic, like the zone itself.

    At most one companion at quantity 1; a resolved card must actually
    have the Companion ability (warning — keyword data can lag). The
    zone sits outside the deck, so nothing here touches deck size.
    """
    companions = deck.companions()
    if not companions:
        return []
    errors: list[ValidationError] = []
    for entry in companions:
        if entry.quantity != 1:
            errors.append(
                ValidationError(
                    "error",
                    f"Companion {entry.card_name}: quantity must be 1",
                    line_number=entry.line_number,
                )
            )
    if len(companions) > 1:
        errors.append(
            ValidationError(
                "error",
                f"Deck has {len(companions)} companions (maximum 1)",
            )
        )
    for entry in companions:
        card = lookup.get(entry.card_name.lower())
        if card is not None and not _has_companion_ability(card):
            errors.append(
                ValidationError(
                    "warning",
                    f"{entry.card_name} is not a companion",
                    line_number=entry.line_number,
                )
            )
    return errors


def _has_companion_ability(card: Card) -> bool:
    if any(k.lower() == "companion" for k in card.keywords):
        return True
    return card.oracle_text.lower().startswith("companion —")


def _check_commander(
    deck: Deck, lookup: dict[str, Card], rules: FormatRules
) -> list[ValidationError]:
    """Commander presence, count, legendary status, and color identity."""
    commanders = deck.commanders()
    if not commanders:
        return [
            ValidationError(
                "error", "No commander (add a CMD: line)"
            )
        ]

    errors: list[ValidationError] = []
    for entry in commanders:
        if entry.quantity != 1:
            errors.append(
                ValidationError(
                    "error",
                    f"Commander {entry.card_name}: quantity must be 1",
                    line_number=entry.line_number,
                )
            )
    if len(commanders) > 2:
        errors.append(
            ValidationError(
                "error",
                f"Deck has {len(commanders)} commanders (maximum 2, as partners)",
            )
        )

    resolved_commanders: list[tuple[DeckEntry, Card]] = []
    for entry in commanders:
        card = lookup.get(entry.card_name.lower())
        if card is None:
            continue  # unknown-name warning already covers it
        resolved_commanders.append((entry, card))
        if "Legendary" not in card.type_line:
            errors.append(
                ValidationError(
                    "error",
                    f"{entry.card_name} is not legendary",
                    line_number=entry.line_number,
                )
            )

    if len(commanders) == 2 and len(resolved_commanders) == 2:
        pair = (resolved_commanders[0][1], resolved_commanders[1][1])
        if not _partner_pair_ok(*pair):
            errors.append(
                ValidationError(
                    "warning",
                    f"{pair[0].name} and {pair[1].name} may not be a legal "
                    "commander pair (no partner ability)",
                )
            )

    if not resolved_commanders:
        return errors

    identity = {
        color
        for _, card in resolved_commanders
        for color in card.color_identity
    }
    for entry in deck.mainboard():
        card = lookup.get(entry.card_name.lower())
        if card is None:
            continue
        if not set(card.color_identity) <= identity:
            errors.append(
                ValidationError(
                    "error",
                    f"{entry.card_name} is outside commander color identity",
                    line_number=entry.line_number,
                )
            )
    return errors


# Abilities that allow a second commander. "Partner with" and plain
# "Partner" both surface as the "Partner" keyword on Scryfall data.
_PARTNER_KEYWORDS = frozenset(
    {"partner", "friends forever", "doctor's companion", "choose a background"}
)


def _partner_pair_ok(a: Card, b: Card) -> bool:
    """Best-effort check that two commanders can legally pair.

    True when both carry a partner-style keyword, or when one card says
    "Choose a Background" and the other is a Background. Exotic pairings
    the heuristic misses only ever produce a warning, never an error.
    """
    def has_partner_ability(card: Card) -> bool:
        keywords = {k.lower() for k in card.keywords}
        if keywords & _PARTNER_KEYWORDS:
            return True
        return "choose a background" in card.oracle_text.lower()

    def is_background(card: Card) -> bool:
        return "Background" in card.type_line

    if has_partner_ability(a) and has_partner_ability(b):
        return True
    if has_partner_ability(a) and is_background(b):
        return True
    return has_partner_ability(b) and is_background(a)

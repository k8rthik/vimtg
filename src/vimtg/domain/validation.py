"""Deck validation rules — the single implementation.

Used by both the CLI (vimtg validate) and the editor (:validate) so the
two can never disagree about what a legal deck looks like. When a format
is supplied, per-card Scryfall legalities and per-format construction
rules (deck size, copy limit, commander) are checked as well.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from vimtg.domain.card_names import CardMap, normalize_card_name
from vimtg.domain.card_types import is_basic_land
from vimtg.domain.deck import Deck, DeckEntry, DeckSection
from vimtg.domain.formats import FormatRules, get_format_rules, known_formats

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from vimtg.domain.card import Card
    from vimtg.domain.deck_lines import MissingQuantityLine

# Sections whose entries count toward deck size / copy limits.
# Maybeboard is a scratchpad outside the deck proper.
_COUNTED_SECTIONS = (DeckSection.MAIN, DeckSection.SIDEBOARD)

# Sections that count toward per-card copy limits. The commander is part
# of the deck: CMD: Atraxa plus a mainboard Atraxa is two copies.
_COPY_SECTIONS = (
    DeckSection.MAIN, DeckSection.SIDEBOARD, DeckSection.COMMANDER,
)


# ValidationError.code for a card name the card database doesn't know —
# lets `vimtg validate --strict` and other callers single it out.
UNKNOWN_CARD = "unknown-card"


@dataclass(frozen=True)
class ValidationError:
    level: str  # "error" or "warning"
    message: str
    line_number: int | None = None
    # Machine-readable kind ("" when unclassified), e.g. UNKNOWN_CARD
    code: str = ""


# ValidationError.code for a card written without a quantity
MISSING_QUANTITY = "missing-quantity"


def missing_quantity_warnings(
    lines: Iterable[MissingQuantityLine], known: Mapping[str, Card] | None
) -> list[ValidationError]:
    """A warning for each quantity-less line that surely means a card: one
    written 'Nx Name', or (with card data, `known`) one naming a known
    card. Other lines stay prose."""
    lookup = CardMap(known) if known else None
    warnings: list[ValidationError] = []
    for missing in lines:
        if missing.count:
            hint = f"drop the x ({missing.fixed})"
        elif lookup is not None and missing.card_name in lookup:
            hint = f"add a quantity ({missing.fixed})"
        else:
            continue
        warnings.append(
            ValidationError(
                "warning", f"not a card line: {hint}", missing.line_number, MISSING_QUANTITY
            )
        )
    return warnings


@dataclass(frozen=True)
class ValidationReport:
    """What `vimtg validate` and :validate report for a deck; each
    surface words it its own way (`file:12: error: …`, `E L12: …`)."""

    fmt: str  # the format checked ('' for the generic rules)
    problems: tuple[ValidationError, ...]
    legality_checked: bool  # False without a card database
    bracket: str = ""  # Commander-bracket estimate, '' when it does not apply


def legality_skipped_note(reason: str, sync: str) -> str:
    """The note for a report without card data: `reason` says why there
    is none, `sync` is the surface's way to get it (":sync")."""
    return f"{reason} — legality checks skipped; run {sync}"


def validation_report(
    deck: Deck,
    resolved: Mapping[str, Card] | None,
    fmt: str,
    missing_quantity: Iterable[MissingQuantityLine] = (),
) -> ValidationReport:
    """Validate `deck` against `fmt`; `resolved` None means there is no
    card database, so card names and legality go unchecked. `missing_quantity`
    (cards written without a quantity) are warned about as well."""
    lookup = None if resolved is None else CardMap(resolved)
    problems = validate_deck(deck, lookup, fmt, card_db=lookup is not None)
    problems += missing_quantity_warnings(missing_quantity, lookup)
    return ValidationReport(
        fmt, tuple(problems), lookup is not None, _bracket_note(deck, fmt, lookup)
    )


def _bracket_note(deck: Deck, fmt: str, resolved: CardMap | None) -> str:
    """Commander-bracket estimate, or '' when it does not apply (not
    Commander, or no card database to read Game Changers)."""
    from vimtg.domain.analytics import estimate_bracket, is_commander_deck

    if resolved is None:
        return ""
    applies = fmt.strip().lower() == "commander" if fmt else is_commander_deck(deck)
    if not applies:
        return ""
    est = estimate_bracket(deck, resolved)
    names = f" ({', '.join(est.game_changers)})" if est.game_changers else ""
    return (
        f"{est.count} Game Changers{names}; estimated Commander bracket "
        f"{est.label} (heuristic: counts Game Changers only)"
    )


def validate_deck(
    deck: Deck,
    resolved: dict[str, Card] | None = None,
    fmt: str = "",
    *,
    card_db: bool | None = None,
) -> list[ValidationError]:
    """Validate deck structure and (when `fmt` is set) format legality.

    Pass `resolved` (card-name lookups) to also flag unknown names and
    run per-card legality checks. `card_db` says whether a card database
    was consulted; when None it is inferred from `resolved` being
    non-empty (an empty dict then means "no card database" and skips
    those checks). Pass card_db=True when lookups ran so a deck whose
    names *all* failed to resolve still reports them. `fmt` empty or
    unknown falls back to the generic 60-card constructed rules.
    """
    errors: list[ValidationError] = []
    lookup = _lowercase_lookup(resolved)
    have_db = bool(lookup) if card_db is None else card_db

    for entry in deck.entries:
        if entry.quantity <= 0:
            errors.append(
                ValidationError(
                    "error",
                    f"Invalid quantity {entry.quantity} for {entry.card_name}",
                    line_number=entry.line_number,
                )
            )

    if have_db:
        for entry in deck.entries:
            if entry.card_name.lower() not in lookup:
                errors.append(
                    ValidationError(
                        "warning",
                        f"Card not found: {entry.card_name}",
                        line_number=entry.line_number,
                        code=UNKNOWN_CARD,
                    )
                )

    errors.extend(_check_companion(deck, lookup))
    errors.extend(_check_plans(deck, fmt))

    rules = get_format_rules(fmt)
    if rules is None:
        if fmt.strip():
            errors.append(
                ValidationError(
                    "warning",
                    f"Unknown format: {fmt.strip()} "
                    f"(supported: {', '.join(known_formats())})",
                )
            )
        errors.extend(_generic_checks(deck, lookup))
        return errors

    errors.extend(_check_legality(deck, lookup, rules))
    errors.extend(_check_copy_limit(deck, lookup, rules))
    errors.extend(_check_deck_size(deck, rules))
    errors.extend(_check_sideboard(deck, rules))
    if rules.requires_commander:
        errors.extend(_check_commander(deck, lookup, rules))
        errors.extend(_check_companion_identity(deck, lookup))
    return errors


def _check_plans(deck: Deck, fmt: str) -> list[ValidationError]:
    """Sideboard-plan checks (imported lazily: sideboard_plan needs
    ValidationError from this module)."""
    from vimtg.domain.sideboard_plan import validate_plans

    return validate_plans(deck, fmt if fmt.strip() else None)


def _lowercase_lookup(
    resolved: dict[str, Card] | None,
) -> dict[str, Card]:
    """Key resolved cards by normalised name (see card_names).

    Whatever map the caller passes, a hand-typed 'lightning bolt' or
    'Fire/Ice' must still find its Card here.
    """
    if not resolved:
        return {}
    return CardMap(resolved)


def _card_key(name: str, lookup: dict[str, Card]) -> str:
    """Identity of the card a deck line names, for copy counting.

    The resolved card's oracle id when known, so 'Fire // Ice' +
    'Fire/Ice' and 'Delver of Secrets' + 'Insectile Aberration' are one
    card; otherwise the normalised name ('Lightning Bolt' and 'lightning
    bolt' still meet).
    """
    card = lookup.get(name)
    if card is not None:
        if card.oracle_id:
            return f"oracle:{card.oracle_id}"
        return normalize_card_name(card.name)
    return normalize_card_name(name)


def _counted_copies(
    deck: Deck, lookup: dict[str, Card]
) -> dict[str, int]:
    """Total copies per card across mainboard, sideboard, commander,
    keyed by _card_key: '4 Lightning Bolt' + '4 lightning bolt' is 8
    copies of one card, not two clean playsets."""
    combined: dict[str, int] = {}
    for entry in deck.entries:
        if entry.section in _COPY_SECTIONS:
            key = _card_key(entry.card_name, lookup)
            combined[key] = combined.get(key, 0) + entry.quantity
    return combined


def _display_names(deck: Deck, lookup: dict[str, Card]) -> dict[str, str]:
    """First-seen original spelling per card key, for messages."""
    names: dict[str, str] = {}
    for entry in deck.entries:
        names.setdefault(_card_key(entry.card_name, lookup), entry.card_name)
    return names


def _generic_checks(
    deck: Deck, lookup: dict[str, Card]
) -> list[ValidationError]:
    """Format-agnostic rules: 4-of, 60-card minimum, 15-card sideboard."""
    errors: list[ValidationError] = []

    display = _display_names(deck, lookup)
    for key, qty in _counted_copies(deck, lookup).items():
        name = display[key]
        if qty > _copy_limit_for(name, lookup.get(name), 4):
            errors.append(
                ValidationError("warning", f"More than 4 copies of {name}")
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

    side_count, note = _sideboard_count(deck)
    if side_count > 15:
        errors.append(
            ValidationError(
                "warning", f"Sideboard has {side_count} cards{note} (maximum 15)"
            )
        )
    return errors


def _sideboard_count(deck: Deck) -> tuple[int, str]:
    """Sideboard size with the companion counted, and a note saying so.

    In formats with a sideboard the companion is one of its (up to 15)
    cards: since the June 2020 companion rules change it is revealed
    from the sideboard (Comprehensive Rules 702.139). A companion
    already listed in SB: is not counted twice.
    """
    side_count = sum(e.quantity for e in deck.sideboard())
    in_side = {e.card_name.lower() for e in deck.sideboard()}
    extra = sum(
        e.quantity for e in deck.companions()
        if e.card_name.lower() not in in_side
    )
    if not extra:
        return side_count, ""
    return side_count + extra, " including the companion"


# Formats where Scryfall's "restricted" means "commander only", not
# "max one copy".
_COMMANDER_ONLY_RESTRICTED = frozenset({"paupercommander"})


def _check_legality(
    deck: Deck, lookup: dict[str, Card], rules: FormatRules
) -> list[ValidationError]:
    """Flag banned / not-legal / restricted-over-limit cards per entry."""
    if not lookup:
        return []
    errors: list[ValidationError] = []
    copies = _counted_copies(deck, lookup)
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
        elif status == "restricted" and rules.name in _COMMANDER_ONLY_RESTRICTED:
            # Scryfall's paupercommander "restricted" = an uncommon
            # creature, legal only in the command zone (PDH rules).
            if entry.section not in (
                DeckSection.COMMANDER, DeckSection.MAYBEBOARD,
            ):
                errors.append(
                    ValidationError(
                        "error",
                        f"{entry.card_name} is legal only as the commander "
                        f"in {rules.name}",
                        line_number=entry.line_number,
                    )
                )
        elif (
            status == "restricted"
            and entry.section in _COPY_SECTIONS
            and copies.get(_card_key(entry.card_name, lookup), 0) > 1
        ):
            errors.append(
                ValidationError(
                    "error",
                    f"{entry.card_name} is restricted (max 1 copy)",
                    line_number=entry.line_number,
                )
            )
    return errors


# Oracle text that overrides the copy limit, e.g. Relentless Rats ("A
# deck can have any number of cards named Relentless Rats.") or Seven
# Dwarves ("A deck can have up to seven cards named Seven Dwarves.").
# Comprehensive Rules 100.2a / 903.5b: such text overrides the 4-of and
# singleton rules.
_ANY_NUMBER_RE = re.compile(r"a deck can have any number of cards named")
_UP_TO_RE = re.compile(r"a deck can have up to (\w+) cards named")
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20,
}


def _copy_limit_for(name: str, card: Card | None, default: int) -> float:
    """Maximum legal copies of a card: basics and "any number" cards are
    unlimited, "up to N cards named" cards allow N, everything else the
    format default. Without card data only the basic-land names are known.
    """
    if is_basic_land(name):
        return float("inf")
    if card is None:
        return default
    if card.type_line.startswith("Basic "):
        return float("inf")
    text = card.oracle_text.lower()
    if _ANY_NUMBER_RE.search(text):
        return float("inf")
    match = _UP_TO_RE.search(text)
    if match:
        word = match.group(1)
        n = _NUMBER_WORDS.get(word) or (int(word) if word.isdigit() else 0)
        if n:
            return max(n, default)
    return default


def _check_copy_limit(
    deck: Deck, lookup: dict[str, Card], rules: FormatRules
) -> list[ValidationError]:
    """Flag every entry-line of a card exceeding the format's copy limit."""
    copies = _counted_copies(deck, lookup)
    display = _display_names(deck, lookup)
    limits = {
        key: _copy_limit_for(display[key], lookup.get(display[key]), rules.copy_limit)
        for key in copies
    }
    over = {key for key, qty in copies.items() if qty > limits[key]}
    if not over:
        return []

    def describe(key: str) -> str:
        limit = int(limits[key])
        word = "copy" if limit == 1 else "copies"
        return f"max {limit} {word} in {rules.name}"

    errors: list[ValidationError] = []
    for entry in deck.entries:
        key = _card_key(entry.card_name, lookup)
        if key in over and entry.section in _COPY_SECTIONS:
            errors.append(
                ValidationError(
                    "error",
                    f"{entry.card_name}: {copies[key]} copies ({describe(key)})",
                    line_number=entry.line_number,
                )
            )
    return errors


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
    side_count, note = _sideboard_count(deck)
    if side_count > rules.max_sideboard:
        return [
            ValidationError(
                "error",
                f"Sideboard has {side_count} cards{note} "
                f"(maximum {rules.max_sideboard} in {rules.name})",
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


def _front_type(card: Card) -> str:
    """Type line of the front face (DFC type lines join faces with //)."""
    return card.type_line.split("//")[0]


def _says_can_be_commander(card: Card) -> bool:
    return "can be your commander" in card.oracle_text.lower()


def _creature_off_battlefield(card: Card) -> bool:
    """Grist, the Hunger Tide and friends: "As long as ~ isn't on the
    battlefield, it's a 1/1 Insect creature" makes the card a creature
    card in the library and command zone, so it can be a commander."""
    text = card.oracle_text.lower()
    return "isn't on the battlefield, it's a" in text and "creature" in text


def _is_background(card: Card) -> bool:
    return "Background" in _front_type(card)


def _chooses_background(card: Card) -> bool:
    keywords = {k.lower() for k in card.keywords}
    return (
        "choose a background" in keywords
        or "choose a background" in card.oracle_text.lower()
    )


def _commander_eligibility(card: Card, fmt: str) -> str | None:
    """Why `card` can't lead a deck in `fmt` (None when it can).

    Comprehensive Rules 903.3: a legendary creature, Vehicle, or
    Spacecraft with a power/toughness box (Edge of Eternities update), or
    a card whose text says it "can be your commander". Brawl also allows
    legendary planeswalkers; Pauper Commander drops the legendary
    requirement (rarity is left to Scryfall's paupercommander legality).
    Backgrounds are eligible only beside a "Choose a Background"
    commander, which the pair check decides. Oathbreaker is separate.
    """
    if _says_can_be_commander(card):
        return None
    front = _front_type(card)
    legendary = "Legendary" in front
    if _is_background(card) and legendary:
        return None  # pairing requirement checked with the partner
    bodied = (
        "Creature" in front
        or _creature_off_battlefield(card)
        or "Vehicle" in front
        or ("Spacecraft" in front and card.power is not None)
    )
    if fmt in _PLANESWALKER_COMMANDER_FORMATS and "Planeswalker" in front:
        bodied = True
    if fmt in _NONLEGENDARY_COMMANDER_FORMATS:
        return None if bodied else "is not a creature"
    if not legendary:
        return "is not legendary"
    if not bodied:
        kinds = (
            "creature or planeswalker"
            if fmt in _PLANESWALKER_COMMANDER_FORMATS
            else "creature"
        )
        return f"is not a legendary {kinds}"
    return None


# Brawl commanders may be legendary planeswalkers
# (https://magic.wizards.com/en/formats/brawl).
_PLANESWALKER_COMMANDER_FORMATS = frozenset({"brawl", "standardbrawl"})
# Pauper Commander: any creature printed at uncommon — no legendary need
# (PDH Home Base rules).
_NONLEGENDARY_COMMANDER_FORMATS = frozenset({"paupercommander"})


def _check_commander(
    deck: Deck, lookup: dict[str, Card], rules: FormatRules
) -> list[ValidationError]:
    """Commander presence, count, eligibility, and color identity."""
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

    oathbreaker = rules.name == "oathbreaker"
    max_cmd = 4 if oathbreaker else 2
    if len(commanders) > max_cmd:
        detail = (
            "two Oathbreakers with their Signature Spells"
            if oathbreaker
            else "as partners"
        )
        errors.append(
            ValidationError(
                "error",
                f"Deck has {len(commanders)} commanders "
                f"(maximum {max_cmd}, {detail})",
            )
        )

    resolved_commanders: list[tuple[DeckEntry, Card]] = [
        (entry, card)
        for entry in commanders
        if (card := lookup.get(entry.card_name.lower())) is not None
    ]  # unknown names: the card-not-found warning already covers them

    signature_spells: list[tuple[DeckEntry, Card]] = []
    if oathbreaker:
        leaders, signature_spells, oath_errors = _check_oathbreaker_zone(
            resolved_commanders
        )
        errors.extend(oath_errors)
    else:
        leaders = resolved_commanders
        for entry, card in resolved_commanders:
            reason = _commander_eligibility(card, rules.name)
            if reason is not None:
                errors.append(
                    ValidationError(
                        "error",
                        f"{entry.card_name} {reason} "
                        "and can't be your commander",
                        line_number=entry.line_number,
                    )
                )
        errors.extend(_check_background_pairing(resolved_commanders))

    if len(leaders) == 2:
        pair = (leaders[0][1], leaders[1][1])
        if not (_is_background(pair[0]) or _is_background(pair[1])) and (
            not _partner_pair_ok(*pair)
        ):
            errors.append(
                ValidationError(
                    "warning",
                    f"{pair[0].name} and {pair[1].name} may not be a legal "
                    "commander pair (no partner ability)",
                )
            )

    if not leaders or len(resolved_commanders) != len(commanders):
        # No identity, or an unknown one while a commander name is
        # unresolved (its card-not-found warning already says so);
        # _check_companion_identity makes the same call
        return errors

    identity = {color for _, card in leaders for color in card.color_identity}
    checked = list(deck.mainboard()) + [e for e, _ in signature_spells]
    for entry in checked:
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


def _check_background_pairing(
    commanders: list[tuple[DeckEntry, Card]],
) -> list[ValidationError]:
    """A Background is only a commander beside a "Choose a Background"
    creature (Comprehensive Rules 702.124k). Error, not warning: unlike
    the partner heuristics this reads unambiguous type-line data."""
    errors: list[ValidationError] = []
    for entry, card in commanders:
        if not _is_background(card) or _says_can_be_commander(card):
            continue
        others = [c for e, c in commanders if e is not entry]
        if not any(_chooses_background(c) for c in others):
            errors.append(
                ValidationError(
                    "error",
                    f"{entry.card_name} is a Background and needs a "
                    "\"Choose a Background\" commander",
                    line_number=entry.line_number,
                )
            )
    return errors


def _check_oathbreaker_zone(
    commanders: list[tuple[DeckEntry, Card]],
) -> tuple[
    list[tuple[DeckEntry, Card]],
    list[tuple[DeckEntry, Card]],
    list[ValidationError],
]:
    """Oathbreaker command zone: planeswalker Oathbreaker(s) plus one
    instant/sorcery Signature Spell each (https://oathbreakermtg.org/rules/).

    Returns (Oathbreakers, Signature Spells, errors); the Oathbreakers'
    identity rules the deck.
    """
    errors: list[ValidationError] = []
    walkers: list[tuple[DeckEntry, Card]] = []
    spells: list[tuple[DeckEntry, Card]] = []
    for entry, card in commanders:
        front = _front_type(card)
        if "Planeswalker" in front:
            walkers.append((entry, card))
        elif "Instant" in front or "Sorcery" in front:
            spells.append((entry, card))
        else:
            errors.append(
                ValidationError(
                    "error",
                    f"{entry.card_name} is neither a planeswalker "
                    "(Oathbreaker) nor an instant/sorcery (Signature Spell)",
                    line_number=entry.line_number,
                )
            )
    if commanders and not walkers:
        errors.append(
            ValidationError("error", "No Oathbreaker (planeswalker) in CMD:")
        )
    if walkers and len(spells) < len(walkers):
        errors.append(
            ValidationError(
                "error",
                f"{len(walkers)} Oathbreaker(s) but {len(spells)} Signature "
                "Spell(s) in CMD: (each Oathbreaker needs one)",
            )
        )
    if len(spells) > max(len(walkers), 1):
        errors.append(
            ValidationError(
                "error",
                f"{len(spells)} Signature Spells for {len(walkers)} "
                "Oathbreaker(s) (one each)",
            )
        )
    return walkers, spells, errors


def _check_companion_identity(
    deck: Deck, lookup: dict[str, Card]
) -> list[ValidationError]:
    """In commander-style formats a companion must fit the commander's
    color identity (Comprehensive Rules 903.11: a card brought in from
    outside the game can't have a color outside the commander's color
    identity). Skipped while any commander is unresolved, since the
    identity is then unknown.
    """
    cards = [lookup.get(e.card_name.lower()) for e in deck.commanders()]
    resolved = [c for c in cards if c is not None]
    if not resolved or len(resolved) != len(cards):
        return []
    identity = {
        color
        for card in resolved
        if not _is_signature_spell(card)
        for color in card.color_identity
    }
    return [
        ValidationError(
            "error",
            f"Companion {entry.card_name} is outside commander "
            "color identity",
            line_number=entry.line_number,
        )
        for entry in deck.companions()
        if (card := lookup.get(entry.card_name.lower())) is not None
        and not set(card.color_identity) <= identity
    ]


def _is_signature_spell(card: Card) -> bool:
    front = _front_type(card)
    return "Instant" in front or "Sorcery" in front


# Abilities that allow a second commander. "Partner with" and plain
# "Partner" both surface as the "Partner" keyword on Scryfall data.
# Backgrounds pair via _check_background_pairing instead.
_PARTNER_KEYWORDS = frozenset(
    {"partner", "partner with", "friends forever"}
)


def _partner_pair_ok(a: Card, b: Card) -> bool:
    """Best-effort check that two commanders can legally pair.

    True when both share a partner-style keyword, or when one is a Time
    Lord Doctor beside a "Doctor's companion". Exotic pairings the
    heuristic misses only ever produce a warning, never an error.
    """
    def keywords(card: Card) -> set[str]:
        return {k.lower() for k in card.keywords}

    def is_doctor(card: Card) -> bool:
        return "Time Lord Doctor" in _front_type(card)

    ka, kb = keywords(a), keywords(b)
    if "doctor's companion" in ka and is_doctor(b):
        return True
    if "doctor's companion" in kb and is_doctor(a):
        return True
    # Partner pairs with Partner, Friends forever with Friends forever
    return bool(ka & kb & _PARTNER_KEYWORDS)

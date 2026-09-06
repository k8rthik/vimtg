"""Sideboard plans — per-matchup boarding maps ('VS:' blocks).

A plan names a matchup and lists what leaves the mainboard ('-N Card')
and what comes in from the sideboard ('+N Card'). Pure data and pure
functions over Deck; the grammar lives in deck_lines, the parser in
data.deck_repository.

TUI-agnostic: no Textual imports.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from vimtg.domain.deck import Deck, DeckEntry, DeckSection
from vimtg.domain.formats import get_format_rules
from vimtg.domain.validation import ValidationError

SIGN_OUT = "-"
SIGN_IN = "+"


@dataclass(frozen=True)
class PlanEntry:
    """One boarding line. `sign` is '-' (out of main), '+' (in from
    side), or '' for a line that has no sign yet (a lint error)."""

    card_name: str
    quantity: int
    sign: str
    comment: str = ""
    line_number: int | None = None

    @property
    def delta(self) -> int:
        if self.sign == SIGN_OUT:
            return -self.quantity
        if self.sign == SIGN_IN:
            return self.quantity
        return 0

    def text(self) -> str:
        """Canonical '-4 Card  // comment' form (no indent)."""
        suffix = f"  // {self.comment}" if self.comment else ""
        return f"{self.sign}{self.quantity} {self.card_name}{suffix}"


@dataclass(frozen=True)
class SideboardPlan:
    name: str
    entries: tuple[PlanEntry, ...] = ()
    note: str = ""
    line_number: int | None = None

    def outs(self) -> tuple[PlanEntry, ...]:
        return tuple(e for e in self.entries if e.sign == SIGN_OUT)

    def ins(self) -> tuple[PlanEntry, ...]:
        return tuple(e for e in self.entries if e.sign == SIGN_IN)

    @property
    def out_total(self) -> int:
        return sum(e.quantity for e in self.outs())

    @property
    def in_total(self) -> int:
        return sum(e.quantity for e in self.ins())

    @property
    def is_balanced(self) -> bool:
        return self.out_total == self.in_total

    def summary(self) -> str:
        """'-6 +6' — the running totals as shown in headers and status."""
        return f"-{self.out_total} +{self.in_total}"


def find_plan(deck: Deck, name: str) -> SideboardPlan | None:
    """The deck's plan named `name`, matched case-insensitively."""
    wanted = name.strip().lower()
    for plan in deck.plans:
        if plan.name.lower() == wanted:
            return plan
    return None


def plan_deltas(plan: SideboardPlan) -> dict[tuple[str, DeckSection], int]:
    """Net copies each card gains or loses, keyed by (name, zone).

    Outs are keyed to the mainboard, ins to the sideboard, so a card
    living in both zones ('2 Skullcrack' main and side) annotates
    each line with its own delta.
    """
    deltas: dict[tuple[str, DeckSection], int] = {}
    for entry in plan.entries:
        if entry.sign == SIGN_OUT:
            key = (entry.card_name, DeckSection.MAIN)
        elif entry.sign == SIGN_IN:
            key = (entry.card_name, DeckSection.SIDEBOARD)
        else:
            continue
        deltas[key] = deltas.get(key, 0) + entry.delta
    return deltas


def _adjust(
    entries: list[DeckEntry], name: str, section: DeckSection, delta: int
) -> list[DeckEntry]:
    """Add `delta` copies of `name` in `section` (matching names
    case-insensitively), dropping the entry at zero and appending a
    fresh one when the card is not there yet. Returns a new list."""
    lowered = name.lower()
    out: list[DeckEntry] = []
    found = False
    for e in entries:
        if e.section == section and e.card_name.lower() == lowered and not found:
            found = True
            qty = e.quantity + delta
            if qty > 0:
                out.append(replace(e, quantity=qty))
            continue
        out.append(e)
    if not found and delta > 0:
        out.append(DeckEntry(quantity=delta, card_name=name, section=section))
    return out


def apply_plan(deck: Deck, plan: SideboardPlan) -> Deck:
    """The post-board configuration: mainboard minus outs plus ins,
    sideboard minus ins plus outs. Returns a NEW Deck; plans are
    dropped from it (a boarded deck has no further plans)."""
    entries = list(deck.entries)
    for e in plan.outs():
        entries = _adjust(entries, e.card_name, DeckSection.MAIN, -e.quantity)
        entries = _adjust(entries, e.card_name, DeckSection.SIDEBOARD, e.quantity)
    for e in plan.ins():
        entries = _adjust(entries, e.card_name, DeckSection.SIDEBOARD, -e.quantity)
        entries = _adjust(entries, e.card_name, DeckSection.MAIN, e.quantity)
    return replace(deck, entries=tuple(entries), plans=())


# ── Validation ────────────────────────────────────────────


def _zone_copies(deck: Deck, section: DeckSection) -> dict[str, int]:
    copies: dict[str, int] = {}
    for e in deck.entries:
        if e.section == section:
            key = e.card_name.lower()
            copies[key] = copies.get(key, 0) + e.quantity
    return copies


def _check_entry(
    entry: PlanEntry,
    plan: SideboardPlan,
    main: dict[str, int],
    side: dict[str, int],
) -> ValidationError | None:
    if entry.sign == "":
        return ValidationError(
            "error",
            f"{entry.quantity} {entry.card_name}: plan lines need + or - "
            f"(-N out of the mainboard, +N in from the sideboard)",
            line_number=entry.line_number,
        )
    zone, copies = (
        ("mainboard", main) if entry.sign == SIGN_OUT else ("sideboard", side)
    )
    available = copies.get(entry.card_name.lower())
    if available is None:
        return ValidationError(
            "error",
            f"{entry.card_name} is not in the {zone}",
            line_number=entry.line_number,
        )
    if entry.quantity > available:
        return ValidationError(
            "error",
            f"{entry.sign}{entry.quantity} {entry.card_name}: "
            f"only {available} in the {zone}",
            line_number=entry.line_number,
        )
    return None


def _check_plan(
    plan: SideboardPlan, main: dict[str, int], side: dict[str, int]
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    seen: set[tuple[str, str]] = set()
    entries_ok = True
    for entry in plan.entries:
        err = _check_entry(entry, plan, main, side)
        if err is not None:
            errors.append(err)
            entries_ok = False
            continue
        key = (entry.sign, entry.card_name.lower())
        if key in seen:
            errors.append(ValidationError(
                "warning",
                f"{entry.sign}{entry.quantity} {entry.card_name} listed twice "
                f"in vs {plan.name}",
                line_number=entry.line_number,
            ))
        seen.add(key)
    # Balance only means something once every line is a real swap
    if entries_ok and not plan.is_balanced:
        errors.append(ValidationError(
            "warning",
            f"vs {plan.name}: {plan.summary()} (unbalanced)",
            line_number=plan.line_number,
        ))
    return errors


def validate_plans(deck: Deck, fmt: str | None = None) -> list[ValidationError]:
    """Lint every plan against the deck it boards.

    Errors: an out that is not in the mainboard, an in that is not in
    the sideboard, more copies than the zone holds, a missing sign.
    Warnings: ins != outs, duplicate plan names, a card listed twice,
    any plan at all in a format without a sideboard.
    """
    if not deck.plans:
        return []
    rules = get_format_rules(deck.metadata.format if fmt is None else fmt)
    if rules is not None and not rules.allows_sideboard:
        return [
            ValidationError(
                "warning",
                f"{rules.name} has no sideboard",
                line_number=plan.line_number,
            )
            for plan in deck.plans
        ]
    main = _zone_copies(deck, DeckSection.MAIN)
    side = _zone_copies(deck, DeckSection.SIDEBOARD)
    errors: list[ValidationError] = []
    names: set[str] = set()
    for plan in deck.plans:
        key = plan.name.lower()
        if key in names:
            errors.append(ValidationError(
                "warning",
                f"Duplicate plan: {plan.name}",
                line_number=plan.line_number,
            ))
        names.add(key)
        errors.extend(_check_plan(plan, main, side))
    return errors


# ── Export ────────────────────────────────────────────────


def _card_list(entries: tuple[PlanEntry, ...]) -> str:
    return ", ".join(f"{e.quantity} {e.card_name}" for e in entries) or "—"


def format_guide_markdown(deck: Deck) -> str:
    """The article-style sideboard guide: one section per matchup with
    OUT and IN lines. Empty string when the deck has no plans."""
    if not deck.plans:
        return ""
    title = f"{deck.metadata.name} — sideboard guide" if deck.metadata.name else (
        "Sideboard guide"
    )
    lines = [f"# {title}", ""]
    for plan in deck.plans:
        lines.append(f"## vs {plan.name}")
        if plan.note:
            lines.append(f"_{plan.note}_")
        lines.append(f"- OUT: {_card_list(plan.outs())}")
        lines.append(f"- IN: {_card_list(plan.ins())}")
        for entry in plan.entries:
            if entry.comment:
                lines.append(f"  - {entry.card_name}: {entry.comment}")
        lines.append("")
    return "\n".join(lines)

"""Import/export decks in MTGO, Arena, Moxfield, and Archidekt formats."""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING

from vimtg.domain.card import Card
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection

if TYPE_CHECKING:
    from collections.abc import Mapping

    from vimtg.data.card_repository import CardRepository


class DeckFormat(Enum):
    VIMTG = "vimtg"
    MTGO = "mtgo"
    ARENA = "arena"
    MOXFIELD = "moxfield"
    ARCHIDEKT = "archidekt"


def _row_quantity(row: Mapping[str, str | None]) -> int:
    """Read a card quantity from a CSV row, trying 'Count' then 'Quantity'.

    Falls back to 1 for missing, empty, or non-integer cells so a single
    malformed value never aborts the whole import.
    """
    raw = row.get("Count") or row.get("Quantity")
    if raw is None:
        return 1
    try:
        qty = int(str(raw).strip())
    except ValueError:
        return 1
    return qty if qty > 0 else 1


@dataclass(frozen=True)
class CardResolution:
    """Outcome of resolving imported card names against the database.

    `resolved` maps the *input* name (as written in the imported deck) to its
    Card. `suggestions` maps each unresolved name to the closest fuzzy match —
    a hint only; the user's deck text is never rewritten automatically.
    """

    resolved: Mapping[str, Card] = field(default_factory=lambda: MappingProxyType({}))
    unresolved: tuple[str, ...] = ()
    suggestions: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


class ImportExportService:
    """Convert decks between vimtg's native format and popular external formats."""

    def __init__(self, card_repo: CardRepository | None = None) -> None:
        self._card_repo = card_repo

    # ------------------------------------------------------------------
    # Format detection
    # ------------------------------------------------------------------

    def detect_format(self, text: str) -> DeckFormat:
        """Auto-detect deck format from raw text.

        Detection order:
        - Contains '// Deck:' or starts with '//' -> VIMTG
        - Contains '(XXX) NNN' set/collector pattern -> ARENA
        - First line is CSV header with 'Count'/'Quantity' + 'Name' -> CSV
          - 'Section' column present -> MOXFIELD
          - Otherwise -> ARCHIDEKT
        - Fallback -> MTGO
        """
        if "// Deck:" in text or text.lstrip().startswith("//"):
            return DeckFormat.VIMTG
        if re.search(r"\([A-Z0-9]{3,5}\)\s+\d+", text):
            return DeckFormat.ARENA
        first_line = text.split("\n")[0].strip().lower()
        has_qty_header = "count" in first_line or "quantity" in first_line
        if has_qty_header and "name" in first_line:
            if "section" in first_line:
                return DeckFormat.MOXFIELD
            return DeckFormat.ARCHIDEKT
        return DeckFormat.MTGO

    # ------------------------------------------------------------------
    # Import / Export dispatch
    # ------------------------------------------------------------------

    def import_deck(self, text: str, fmt: DeckFormat | None = None) -> Deck:
        """Parse text into a Deck. Auto-detects format when *fmt* is None."""
        if fmt is None:
            fmt = self.detect_format(text)
        match fmt:
            case DeckFormat.VIMTG:
                from vimtg.data.deck_repository import parse_deck_text

                return parse_deck_text(text)
            case DeckFormat.MTGO:
                return self._import_mtgo(text)
            case DeckFormat.ARENA:
                return self._import_arena(text)
            case DeckFormat.MOXFIELD:
                return self._import_moxfield(text)
            case DeckFormat.ARCHIDEKT:
                return self._import_archidekt(text)

    def export_deck(
        self,
        deck: Deck,
        fmt: DeckFormat,
        resolved: dict[str, Card] | None = None,
    ) -> str:
        """Serialize a Deck to the requested format string."""
        match fmt:
            case DeckFormat.VIMTG:
                from vimtg.data.deck_repository import serialize_deck

                return serialize_deck(deck)
            case DeckFormat.MTGO:
                return self._export_mtgo(deck)
            case DeckFormat.ARENA:
                return self._export_arena(deck, resolved or {})
            case DeckFormat.MOXFIELD:
                return self._export_moxfield(deck, resolved or {})
            case DeckFormat.ARCHIDEKT:
                return self._export_archidekt(deck)

    # ------------------------------------------------------------------
    # Card resolution
    # ------------------------------------------------------------------

    def resolve_cards(self, deck: Deck) -> CardResolution:
        """Resolve each unique card name in *deck* against the database.

        Exact and case-insensitive matches resolve directly (get_by_name is
        COLLATE NOCASE). Names with no match are reported as unresolved, with
        the top FTS5 hit recorded as a "did you mean?" suggestion when one
        exists. Returns an empty resolution when no repository is configured.
        """
        if self._card_repo is None:
            return CardResolution()

        resolved: dict[str, Card] = {}
        unresolved: list[str] = []
        suggestions: dict[str, str] = {}
        for name in sorted(deck.unique_card_names()):
            card = self._card_repo.get_by_name(name)
            if card is not None:
                resolved[name] = card
                continue
            unresolved.append(name)
            try:
                hits = self._card_repo.search(name, limit=1)
            except sqlite3.Error:
                hits = []  # suggestion lookup is best-effort
            if hits:
                suggestions[name] = hits[0].name
        return CardResolution(
            resolved=MappingProxyType(resolved),
            unresolved=tuple(unresolved),
            suggestions=MappingProxyType(suggestions),
        )

    # ------------------------------------------------------------------
    # MTGO
    # ------------------------------------------------------------------

    def _import_mtgo(self, text: str) -> Deck:
        """Parse MTGO format: 'N CardName', 'Sideboard' header switches zone."""
        entries: list[DeckEntry] = []
        section = DeckSection.MAIN
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.lower() == "sideboard":
                section = DeckSection.SIDEBOARD
                continue
            m = re.match(r"^(\d+)\s+(.+)$", line)
            if m:
                entries.append(
                    DeckEntry(int(m.group(1)), m.group(2).strip(), section)
                )
        return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())

    def _export_mtgo(self, deck: Deck) -> str:
        lines: list[str] = []
        for e in deck.mainboard():
            lines.append(f"{e.quantity} {e.card_name}")
        if deck.sideboard():
            lines.append("")
            lines.append("Sideboard")
            for e in deck.sideboard():
                lines.append(f"{e.quantity} {e.card_name}")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Arena
    # ------------------------------------------------------------------

    def _import_arena(self, text: str) -> Deck:
        """Parse Arena format: 'N CardName (SET) CollectorNum'."""
        entries: list[DeckEntry] = []
        section = DeckSection.MAIN
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            if low in ("deck", "companion"):
                continue
            if low == "sideboard":
                section = DeckSection.SIDEBOARD
                continue
            if low == "commander":
                section = DeckSection.COMMANDER
                continue
            m = re.match(r"^(\d+)\s+(.+?)(?:\s+\([A-Za-z0-9]{3,5}\)\s*\d*)?$", line)
            if m:
                entries.append(
                    DeckEntry(int(m.group(1)), m.group(2).strip(), section)
                )
        return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())

    @staticmethod
    def _arena_entry(e: DeckEntry, resolved: dict[str, Card]) -> str:
        """Format one Arena line, appending '(SET) 0' when the card resolves."""
        card = resolved.get(e.card_name)
        if card:
            return f"{e.quantity} {e.card_name} ({card.set_code.upper()}) 0"
        return f"{e.quantity} {e.card_name}"

    def _export_arena(self, deck: Deck, resolved: dict[str, Card]) -> str:
        lines: list[str] = ["Deck"]
        lines.extend(self._arena_entry(e, resolved) for e in deck.mainboard())
        if deck.sideboard():
            lines.append("")
            lines.append("Sideboard")
            lines.extend(self._arena_entry(e, resolved) for e in deck.sideboard())
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Moxfield (CSV with Section column)
    # ------------------------------------------------------------------

    def _import_moxfield(self, text: str) -> Deck:
        reader = csv.DictReader(io.StringIO(text))
        entries: list[DeckEntry] = []
        for row in reader:
            qty = _row_quantity(row)
            # DictReader yields None (not the default) for short rows
            name = row.get("Name") or ""
            section_str = (row.get("Section") or "mainboard").lower()
            if "side" in section_str:
                section = DeckSection.SIDEBOARD
            elif "maybe" in section_str:
                section = DeckSection.MAYBEBOARD
            else:
                section = DeckSection.MAIN
            if name:
                entries.append(DeckEntry(qty, name, section))
        return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())

    @staticmethod
    def _moxfield_row(
        e: DeckEntry, resolved: dict[str, Card], section: str
    ) -> list[object]:
        """Build one Moxfield CSV row for a deck entry."""
        card = resolved.get(e.card_name)
        edition = card.set_code.upper() if card else ""
        return [e.quantity, e.card_name, edition, "", section]

    def _export_moxfield(self, deck: Deck, resolved: dict[str, Card]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Count", "Name", "Edition", "Collector Number", "Section"])
        for e in deck.mainboard():
            writer.writerow(self._moxfield_row(e, resolved, "mainboard"))
        for e in deck.sideboard():
            writer.writerow(self._moxfield_row(e, resolved, "sideboard"))
        for e in deck.maybeboard():
            writer.writerow(self._moxfield_row(e, resolved, "maybeboard"))
        return output.getvalue()

    # ------------------------------------------------------------------
    # Archidekt (CSV without Section column)
    # ------------------------------------------------------------------

    def _import_archidekt(self, text: str) -> Deck:
        reader = csv.DictReader(io.StringIO(text))
        entries: list[DeckEntry] = []
        for row in reader:
            qty = _row_quantity(row)
            name = row.get("Name", "")
            if name:
                entries.append(DeckEntry(qty, name, DeckSection.MAIN))
        return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())

    def _export_archidekt(self, deck: Deck) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Quantity", "Name"])
        for e in deck.entries:
            writer.writerow([e.quantity, e.card_name])
        return output.getvalue()

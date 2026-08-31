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
from vimtg.domain.deck_lines import clamp_quantity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from vimtg.data.card_repository import CardRepository


class DeckFormat(Enum):
    VIMTG = "vimtg"
    MTGO = "mtgo"
    MTGO_DEK = "dek"  # MTGO's native .dek XML file
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
    return clamp_quantity(qty) if qty > 0 else 1


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
        stripped = text.lstrip()
        if stripped.startswith(("<?xml", "<Deck")):
            return DeckFormat.MTGO_DEK
        if "// Deck:" in text or stripped.startswith("//"):
            return DeckFormat.VIMTG
        # Native zone markers (prefix lines or block headers) — without
        # this, a comment-less native deck detects as MTGO and its
        # SB:/CMD: lines are silently dropped on import
        if re.search(
            r"^\s*(SB|MB|CMD|CMP|DCK):", text, re.MULTILINE | re.IGNORECASE
        ):
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
            case DeckFormat.MTGO_DEK:
                return self._import_mtgo_dek(text)
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
            case DeckFormat.MTGO_DEK:
                return self._export_mtgo_dek(deck)
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
                    DeckEntry(
                        clamp_quantity(int(m.group(1))),
                        m.group(2).strip(),
                        section,
                    )
                )
        return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())

    def _export_mtgo(self, deck: Deck) -> str:
        lines: list[str] = []
        for e in deck.mainboard():
            lines.append(f"{e.quantity} {e.card_name}")
        # MTGO's text form has no command zone — its convention parks
        # the commander (and companion) in the sideboard, which also
        # keeps them from being silently dropped on conversion
        side = deck.commanders() + deck.companions() + deck.sideboard()
        if side:
            lines.append("")
            lines.append("Sideboard")
            for e in side:
                lines.append(f"{e.quantity} {e.card_name}")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # MTGO .dek (XML)
    # ------------------------------------------------------------------

    def _import_mtgo_dek(self, text: str) -> Deck:
        """Parse MTGO's native .dek XML: <Cards Quantity Sideboard Name/>.

        Malformed XML degrades to an empty deck rather than raising —
        import reports 0 cards and the user's buffer stays intact.
        """
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return Deck(metadata=DeckMetadata(), entries=(), comments=())
        entries: list[DeckEntry] = []
        for node in root.iter("Cards"):
            name = (node.get("Name") or "").strip()
            try:
                qty = int(node.get("Quantity") or 0)
            except ValueError:
                qty = 0
            if not name or qty <= 0:
                continue
            in_side = (node.get("Sideboard") or "").lower() == "true"
            section = DeckSection.SIDEBOARD if in_side else DeckSection.MAIN
            entries.append(DeckEntry(clamp_quantity(qty), name, section))
        return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())

    def _export_mtgo_dek(self, deck: Deck) -> str:
        """Serialize to MTGO's .dek XML. Like the text export, commander
        and companion park in the sideboard so nothing is dropped."""
        from xml.sax.saxutils import quoteattr

        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            "<Deck>",
            "  <NetDeckID>0</NetDeckID>",
            "  <PreconstructedDeckID>0</PreconstructedDeckID>",
        ]
        side = deck.commanders() + deck.companions() + deck.sideboard()
        for entry, in_side in [(e, False) for e in deck.mainboard()] + [
            (e, True) for e in side
        ]:
            flag = "true" if in_side else "false"
            lines.append(
                f'  <Cards Quantity="{entry.quantity}" Sideboard="{flag}" '
                f"Name={quoteattr(entry.card_name)} />"
            )
        lines.append("</Deck>")
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
            if low == "deck":
                section = DeckSection.MAIN
                continue
            if low == "companion":
                section = DeckSection.COMPANION
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
                    DeckEntry(
                        clamp_quantity(int(m.group(1))),
                        m.group(2).strip(),
                        section,
                    )
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
        lines: list[str] = []
        if deck.commanders():
            lines.append("Commander")
            lines.extend(
                self._arena_entry(e, resolved) for e in deck.commanders()
            )
            lines.append("")
        if deck.companions():
            lines.append("Companion")
            lines.extend(
                self._arena_entry(e, resolved) for e in deck.companions()
            )
            lines.append("")
        lines.append("Deck")
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
            elif "commander" in section_str:
                section = DeckSection.COMMANDER
            elif "companion" in section_str:
                section = DeckSection.COMPANION
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
        for e in deck.commanders():
            writer.writerow(self._moxfield_row(e, resolved, "commander"))
        for e in deck.companions():
            writer.writerow(self._moxfield_row(e, resolved, "companion"))
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
            # Maybeboard is a scratchpad outside the deck — flattening
            # it into a sectionless list would merge it into the deck
            # proper on re-import
            if e.section == DeckSection.MAYBEBOARD:
                continue
            writer.writerow([e.quantity, e.card_name])
        return output.getvalue()

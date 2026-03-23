"""Import/export decks in MTGO, Arena, Moxfield, and Archidekt formats."""

from __future__ import annotations

import csv
import io
import re
from enum import Enum
from typing import TYPE_CHECKING

from vimtg.domain.card import Card
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection

if TYPE_CHECKING:
    from vimtg.data.card_repository import CardRepository


class DeckFormat(Enum):
    VIMTG = "vimtg"
    MTGO = "mtgo"
    ARENA = "arena"
    MOXFIELD = "moxfield"
    ARCHIDEKT = "archidekt"


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
            m = re.match(r"^(\d+)\s+(.+?)(?:\s+\([A-Z0-9]+\)\s*\d*)?$", line)
            if m:
                entries.append(
                    DeckEntry(int(m.group(1)), m.group(2).strip(), section)
                )
        return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())

    def _export_arena(self, deck: Deck, resolved: dict[str, Card]) -> str:
        lines: list[str] = ["Deck"]
        for e in deck.mainboard():
            card = resolved.get(e.card_name)
            if card:
                lines.append(
                    f"{e.quantity} {e.card_name} ({card.set_code.upper()}) 0"
                )
            else:
                lines.append(f"{e.quantity} {e.card_name}")
        if deck.sideboard():
            lines.append("")
            lines.append("Sideboard")
            for e in deck.sideboard():
                card = resolved.get(e.card_name)
                if card:
                    lines.append(
                        f"{e.quantity} {e.card_name} ({card.set_code.upper()}) 0"
                    )
                else:
                    lines.append(f"{e.quantity} {e.card_name}")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Moxfield (CSV with Section column)
    # ------------------------------------------------------------------

    def _import_moxfield(self, text: str) -> Deck:
        reader = csv.DictReader(io.StringIO(text))
        entries: list[DeckEntry] = []
        for row in reader:
            qty = int(row.get("Count", row.get("Quantity", "1")))
            name = row.get("Name", "")
            section_str = row.get("Section", "mainboard").lower()
            section = (
                DeckSection.SIDEBOARD if "side" in section_str else DeckSection.MAIN
            )
            if name:
                entries.append(DeckEntry(qty, name, section))
        return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())

    def _export_moxfield(self, deck: Deck, resolved: dict[str, Card]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Count", "Name", "Edition", "Collector Number", "Section"])
        for e in deck.mainboard():
            card = resolved.get(e.card_name)
            edition = card.set_code.upper() if card else ""
            writer.writerow([e.quantity, e.card_name, edition, "", "mainboard"])
        for e in deck.sideboard():
            card = resolved.get(e.card_name)
            edition = card.set_code.upper() if card else ""
            writer.writerow([e.quantity, e.card_name, edition, "", "sideboard"])
        return output.getvalue()

    # ------------------------------------------------------------------
    # Archidekt (CSV without Section column)
    # ------------------------------------------------------------------

    def _import_archidekt(self, text: str) -> Deck:
        reader = csv.DictReader(io.StringIO(text))
        entries: list[DeckEntry] = []
        for row in reader:
            qty = int(row.get("Quantity", row.get("Count", "1")))
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

"""Import/export decks in MTGO, Arena, Moxfield, and Archidekt formats."""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING

from vimtg.domain.card import Card
from vimtg.domain.card_names import CardMap
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
from vimtg.domain.deck_lines import clamp_quantity, strip_bom, strip_printing_suffix
from vimtg.services.deck_sources import (
    SkippedLine,
    archidekt_placement,
    parse_decklist_text,
    primary_archidekt_category,
)

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
    GUIDE = "guide"  # sideboard guide as Markdown — export only


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


def _csv_name(row: Mapping[str, str | None]) -> str:
    """The card name of a CSV row, without any printing suffix."""
    # DictReader yields None (not the default) for short rows
    return strip_printing_suffix(row.get("Name") or "")


def _normalize_text(text: str) -> str:
    """Drop a UTF-8 BOM and fold CRLF/CR line endings to LF."""
    return strip_bom(text).replace("\r\n", "\n").replace("\r", "\n")


def merge_duplicate_entries(deck: Deck) -> Deck:
    """Merge entries naming the same card (ignoring case) in the same
    section and category: 'Lightning Bolt' + 'lightning bolt' become
    one entry with the summed quantity, spelled like the first one.
    Tags are unioned; the first entry's comment wins."""
    merged: dict[tuple[DeckSection, str, str], DeckEntry] = {}
    for e in deck.entries:
        key = (e.section, e.card_name.casefold(), e.category)
        first = merged.get(key)
        if first is None:
            merged[key] = e
            continue
        merged[key] = replace(
            first,
            quantity=clamp_quantity(first.quantity + e.quantity),
            tags=first.tags | e.tags,
            comment=first.comment or e.comment,
        )
    if len(merged) == len(deck.entries):
        return deck
    return replace(deck, entries=tuple(merged.values()))


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


def _client_name(name: str, resolved: Mapping[str, Card]) -> str:
    """front_face_name, using the resolved card's layout when known."""
    return front_face_name(name, resolved.get(name))


@dataclass(frozen=True)
class ImportReport:
    """An imported deck plus every input line the importer could not
    read (instead of dropping them silently)."""

    deck: Deck
    skipped: tuple[SkippedLine, ...] = ()


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
            r"^\s*(SB|MB|CMD|CMP|DCK|VS):", text, re.MULTILINE | re.IGNORECASE
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
        return self.import_deck_report(text, fmt).deck

    def import_deck_report(
        self, text: str, fmt: DeckFormat | None = None
    ) -> ImportReport:
        """Parse text into a Deck and report the lines that were skipped.

        A BOM and CRLF line endings are tolerated in every format, and
        case-insensitive duplicate card names are merged.
        """
        text = _normalize_text(text)
        if fmt is None:
            fmt = self.detect_format(text)
        match fmt:
            case DeckFormat.VIMTG:
                from vimtg.data.deck_repository import parse_deck_text

                skipped: list[SkippedLine] = []
                deck = parse_deck_text(
                    text,
                    on_skip=lambda n, line: skipped.append(SkippedLine(n, line)),
                )
                report = ImportReport(deck, tuple(skipped))
            case DeckFormat.MTGO | DeckFormat.ARENA:
                report = self._import_text(text)
            case DeckFormat.MTGO_DEK:
                report = ImportReport(self._import_mtgo_dek(text))
            case DeckFormat.MOXFIELD:
                report = self._import_moxfield(text)
            case DeckFormat.ARCHIDEKT:
                report = self._import_archidekt(text)
            case DeckFormat.GUIDE:
                raise ValueError("The sideboard guide is an export-only format")
        return replace(report, deck=merge_duplicate_entries(report.deck))

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
                return self._export_mtgo(deck, resolved or {})
            case DeckFormat.MTGO_DEK:
                return self._export_mtgo_dek(deck, resolved or {})
            case DeckFormat.ARENA:
                return self._export_arena(deck, CardMap(resolved or {}))
            case DeckFormat.MOXFIELD:
                return self._export_moxfield(deck, CardMap(resolved or {}))
            case DeckFormat.ARCHIDEKT:
                return self._export_archidekt(deck)
            case DeckFormat.GUIDE:
                from vimtg.domain.sideboard_plan import format_guide_markdown

                return format_guide_markdown(deck)

    # ------------------------------------------------------------------
    # Card resolution
    # ------------------------------------------------------------------

    def resolve_cards(self, deck: Deck) -> CardResolution:
        """Resolve each unique card name in *deck* against the database.

        Names resolve through the card-name resolver (case, accents, face
        names and "Fire/Ice" spellings all match). Names with no match are
        reported as unresolved, with the top FTS5 hit recorded as a "did you
        mean?" suggestion when one exists. Returns an empty resolution when
        no repository is configured.
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
    # MTGO / Arena text
    # ------------------------------------------------------------------

    def _import_text(self, text: str) -> ImportReport:
        """Parse MTGO .txt, Arena, and similar plain-text decklists.

        One parser (deck_sources.parse_decklist_text) handles both, so
        headers, 'Nx' quantities, set/collector/foil suffixes, and the
        MTGO blank-line sideboard divider work whichever format was
        detected or requested.
        """
        remote = parse_decklist_text(text, name="", blank_splits=None)
        deck = remote.deck
        if remote.name:
            deck = replace(deck, metadata=replace(deck.metadata, name=remote.name))
        return ImportReport(deck, remote.skipped)

    def _export_mtgo(self, deck: Deck, resolved: dict[str, Card]) -> str:
        lines: list[str] = []
        for e in deck.mainboard():
            lines.append(f"{e.quantity} {_client_name(e.card_name, resolved)}")
        # MTGO's text form has no command zone — its convention parks
        # the commander (and companion) in the sideboard, which also
        # keeps them from being silently dropped on conversion
        side = deck.commanders() + deck.companions() + deck.sideboard()
        if side:
            lines.append("")
            lines.append("Sideboard")
            for e in side:
                lines.append(f"{e.quantity} {_client_name(e.card_name, resolved)}")
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

    def _export_mtgo_dek(self, deck: Deck, resolved: dict[str, Card]) -> str:
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
                f"Name={quoteattr(_client_name(entry.card_name, resolved))} />"
            )
        lines.append("</Deck>")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Arena
    # ------------------------------------------------------------------

    @staticmethod
    def _arena_entry(e: DeckEntry, resolved: dict[str, Card]) -> str:
        """Format one Arena line: quantity and front-face name.

        No '(SET) N' suffix — vimtg does not track collector numbers,
        and Arena rejects a line whose set/number pair is wrong, while
        a bare name always imports.
        """
        return f"{e.quantity} {_client_name(e.card_name, resolved)}"

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

    def _import_moxfield(self, text: str) -> ImportReport:
        reader = csv.DictReader(io.StringIO(text))
        entries: list[DeckEntry] = []
        skipped: list[SkippedLine] = []
        for row in reader:
            qty = _row_quantity(row)
            name = _csv_name(row)
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
            elif _row_has_content(row):
                skipped.append(_skipped_row(reader, row))
        return ImportReport(_plain_deck(entries), tuple(skipped))

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

    def _import_archidekt(self, text: str) -> ImportReport:
        """Parse Archidekt's CSV export. A 'Categories' (or 'Category')
        column places each card by its first category, exactly like the
        Archidekt URL import: Commander/Companion/Sideboard/Maybeboard
        pick the zone, a user category becomes the @category."""
        reader = csv.DictReader(io.StringIO(text))
        entries: list[DeckEntry] = []
        skipped: list[SkippedLine] = []
        for row in reader:
            qty = _row_quantity(row)
            name = _csv_name(row)
            if not name:
                if _row_has_content(row):
                    skipped.append(_skipped_row(reader, row))
                continue
            categories = row.get("Categories") or row.get("Category") or ""
            section, category = archidekt_placement(primary_archidekt_category(categories))
            entries.append(DeckEntry(qty, name, section, category=category))
        return ImportReport(_plain_deck(entries), tuple(skipped))

    def _export_archidekt(self, deck: Deck) -> str:
        """Quantity/Name/Categories CSV. Zones travel as Archidekt's own
        zone categories so a re-import (here or on Archidekt) keeps the
        commander, sideboard, and maybeboard apart from the deck."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Quantity", "Name", "Categories"])
        for e in deck.entries:
            writer.writerow(
                [e.quantity, e.card_name, _ARCHIDEKT_ZONE_CATEGORY.get(e.section, e.category)]
            )
        return output.getvalue()


# Archidekt category names for the non-main zones (main-deck cards
# carry their @category, if any)
_ARCHIDEKT_ZONE_CATEGORY: dict[DeckSection, str] = {
    DeckSection.COMMANDER: "Commander",
    DeckSection.COMPANION: "Companion",
    DeckSection.SIDEBOARD: "Sideboard",
    DeckSection.MAYBEBOARD: "Maybeboard",
}


def _plain_deck(entries: list[DeckEntry]) -> Deck:
    return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())


def _row_has_content(row: Mapping[str, str | None]) -> bool:
    """False for an all-empty row (',,,,'), which is just a blank line."""
    return any((v or "").strip() for v in row.values() if isinstance(v, str))


def _skipped_row(reader: csv.DictReader[str], row: Mapping[str, str | None]) -> SkippedLine:
    """A CSV row without a card name, reported by its line number."""
    cells = [v for v in row.values() if isinstance(v, str) and v]
    return SkippedLine(reader.line_num, ",".join(cells))

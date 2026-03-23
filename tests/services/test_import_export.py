"""Tests for ImportExportService — format detection, import, export, round-trips."""

from __future__ import annotations

import csv
import io

from vimtg.domain.card import Card, Rarity
from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
from vimtg.services.import_export_service import DeckFormat, ImportExportService

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _svc() -> ImportExportService:
    return ImportExportService()


def _make_card(name: str, set_code: str = "sta") -> Card:
    return Card(
        scryfall_id="test-id",
        name=name,
        mana_cost="{R}",
        cmc=1.0,
        type_line="Instant",
        oracle_text="Deal 3 damage.",
        colors=(),
        color_identity=(),
        power=None,
        toughness=None,
        set_code=set_code,
        rarity=Rarity.COMMON,
        price_usd=None,
        legalities={},
        image_uri=None,
        layout="normal",
        keywords=(),
    )


def _make_deck(
    main: list[tuple[int, str]] | None = None,
    side: list[tuple[int, str]] | None = None,
) -> Deck:
    entries: list[DeckEntry] = []
    for qty, name in (main or []):
        entries.append(DeckEntry(qty, name, DeckSection.MAIN))
    for qty, name in (side or []):
        entries.append(DeckEntry(qty, name, DeckSection.SIDEBOARD))
    return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())


# ==================================================================
# Format detection
# ==================================================================

class TestDetectFormat:
    def test_detect_vimtg_deck_header(self) -> None:
        text = "// Deck: Burn\n4 Lightning Bolt"
        assert _svc().detect_format(text) == DeckFormat.VIMTG

    def test_detect_vimtg_comment_start(self) -> None:
        text = "// just a comment\n4 Lightning Bolt"
        assert _svc().detect_format(text) == DeckFormat.VIMTG

    def test_detect_arena(self) -> None:
        text = "Deck\n4 Lightning Bolt (STA) 62"
        assert _svc().detect_format(text) == DeckFormat.ARENA

    def test_detect_mtgo(self) -> None:
        text = "4 Lightning Bolt\n2 Counterspell"
        assert _svc().detect_format(text) == DeckFormat.MTGO

    def test_detect_moxfield(self) -> None:
        text = "Count,Name,Edition,Collector Number,Section\n4,Lightning Bolt,STA,,mainboard"
        assert _svc().detect_format(text) == DeckFormat.MOXFIELD

    def test_detect_archidekt(self) -> None:
        text = "Quantity,Name\n4,Lightning Bolt"
        assert _svc().detect_format(text) == DeckFormat.ARCHIDEKT


# ==================================================================
# MTGO
# ==================================================================

class TestMTGO:
    def test_import_mtgo(self) -> None:
        text = "4 Lightning Bolt\n2 Counterspell\n\nSideboard\n3 Pyroblast\n"
        deck = _svc().import_deck(text, DeckFormat.MTGO)
        assert len(deck.mainboard()) == 2
        assert len(deck.sideboard()) == 1
        assert deck.mainboard()[0].card_name == "Lightning Bolt"
        assert deck.mainboard()[0].quantity == 4
        assert deck.sideboard()[0].card_name == "Pyroblast"
        assert deck.sideboard()[0].quantity == 3

    def test_export_mtgo(self) -> None:
        deck = _make_deck(
            main=[(4, "Lightning Bolt"), (2, "Counterspell")],
            side=[(3, "Pyroblast")],
        )
        result = _svc().export_deck(deck, DeckFormat.MTGO)
        assert "4 Lightning Bolt" in result
        assert "2 Counterspell" in result
        assert "Sideboard" in result
        assert "3 Pyroblast" in result

    def test_export_mtgo_no_sideboard(self) -> None:
        deck = _make_deck(main=[(4, "Lightning Bolt")])
        result = _svc().export_deck(deck, DeckFormat.MTGO)
        assert "Sideboard" not in result

    def test_roundtrip_mtgo(self) -> None:
        deck = _make_deck(
            main=[(4, "Lightning Bolt"), (2, "Counterspell")],
            side=[(3, "Pyroblast")],
        )
        exported = _svc().export_deck(deck, DeckFormat.MTGO)
        reimported = _svc().import_deck(exported, DeckFormat.MTGO)
        assert reimported.mainboard() == deck.mainboard()
        assert reimported.sideboard() == deck.sideboard()


# ==================================================================
# Arena
# ==================================================================

class TestArena:
    def test_import_arena(self) -> None:
        text = "Deck\n4 Lightning Bolt (STA) 62\n2 Counterspell (STA) 12\n"
        deck = _svc().import_deck(text, DeckFormat.ARENA)
        assert len(deck.mainboard()) == 2
        assert deck.mainboard()[0].card_name == "Lightning Bolt"
        assert deck.mainboard()[1].card_name == "Counterspell"

    def test_import_arena_no_set(self) -> None:
        text = "Deck\n4 Lightning Bolt\n"
        deck = _svc().import_deck(text, DeckFormat.ARENA)
        assert deck.mainboard()[0].card_name == "Lightning Bolt"
        assert deck.mainboard()[0].quantity == 4

    def test_import_arena_with_sideboard(self) -> None:
        text = "Deck\n4 Lightning Bolt (STA) 62\n\nSideboard\n2 Pyroblast (ICE) 212\n"
        deck = _svc().import_deck(text, DeckFormat.ARENA)
        assert len(deck.mainboard()) == 1
        assert len(deck.sideboard()) == 1
        assert deck.sideboard()[0].card_name == "Pyroblast"

    def test_export_arena_with_resolved(self) -> None:
        deck = _make_deck(main=[(4, "Lightning Bolt")])
        resolved = {"Lightning Bolt": _make_card("Lightning Bolt", "sta")}
        result = _svc().export_deck(deck, DeckFormat.ARENA, resolved)
        assert "4 Lightning Bolt (STA) 0" in result
        assert result.startswith("Deck\n")

    def test_export_arena_without_resolved(self) -> None:
        deck = _make_deck(main=[(4, "Lightning Bolt")])
        result = _svc().export_deck(deck, DeckFormat.ARENA)
        assert "4 Lightning Bolt" in result
        assert "(STA)" not in result

    def test_roundtrip_arena(self) -> None:
        """Import Arena text, export back, reimport — card names preserved."""
        text = "Deck\n4 Lightning Bolt (STA) 62\n2 Counterspell (STA) 12\n"
        deck = _svc().import_deck(text, DeckFormat.ARENA)
        exported = _svc().export_deck(deck, DeckFormat.ARENA)
        reimported = _svc().import_deck(exported, DeckFormat.ARENA)
        assert reimported.mainboard() == deck.mainboard()


# ==================================================================
# Moxfield
# ==================================================================

class TestMoxfield:
    def test_import_moxfield(self) -> None:
        text = (
            "Count,Name,Edition,Collector Number,Section\n"
            "4,Lightning Bolt,STA,,mainboard\n"
            "2,Pyroblast,ICE,,sideboard\n"
        )
        deck = _svc().import_deck(text, DeckFormat.MOXFIELD)
        assert len(deck.mainboard()) == 1
        assert len(deck.sideboard()) == 1
        assert deck.mainboard()[0].quantity == 4

    def test_export_moxfield(self) -> None:
        deck = _make_deck(main=[(4, "Lightning Bolt")])
        result = _svc().export_deck(deck, DeckFormat.MOXFIELD)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["Count"] == "4"
        assert rows[0]["Name"] == "Lightning Bolt"
        assert rows[0]["Section"] == "mainboard"

    def test_moxfield_comma_in_name(self) -> None:
        text = (
            'Count,Name,Edition,Collector Number,Section\n'
            '2,"Liliana, the Last Hope",EMN,,mainboard\n'
        )
        deck = _svc().import_deck(text, DeckFormat.MOXFIELD)
        assert deck.mainboard()[0].card_name == "Liliana, the Last Hope"
        assert deck.mainboard()[0].quantity == 2

    def test_export_moxfield_with_resolved(self) -> None:
        deck = _make_deck(
            main=[(4, "Lightning Bolt")],
            side=[(2, "Pyroblast")],
        )
        resolved = {
            "Lightning Bolt": _make_card("Lightning Bolt", "sta"),
            "Pyroblast": _make_card("Pyroblast", "ice"),
        }
        result = _svc().export_deck(deck, DeckFormat.MOXFIELD, resolved)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert rows[0]["Edition"] == "STA"
        assert rows[1]["Edition"] == "ICE"
        assert rows[1]["Section"] == "sideboard"

    def test_roundtrip_moxfield(self) -> None:
        deck = _make_deck(
            main=[(4, "Lightning Bolt")],
            side=[(2, "Pyroblast")],
        )
        exported = _svc().export_deck(deck, DeckFormat.MOXFIELD)
        reimported = _svc().import_deck(exported, DeckFormat.MOXFIELD)
        assert reimported.mainboard() == deck.mainboard()
        assert reimported.sideboard() == deck.sideboard()


# ==================================================================
# Archidekt
# ==================================================================

class TestArchidekt:
    def test_import_archidekt(self) -> None:
        text = "Quantity,Name\n4,Lightning Bolt\n2,Counterspell\n"
        deck = _svc().import_deck(text, DeckFormat.ARCHIDEKT)
        assert len(deck.entries) == 2
        assert deck.entries[0].card_name == "Lightning Bolt"
        assert deck.entries[1].quantity == 2

    def test_export_archidekt(self) -> None:
        deck = _make_deck(main=[(4, "Lightning Bolt")], side=[(2, "Pyroblast")])
        result = _svc().export_deck(deck, DeckFormat.ARCHIDEKT)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["Quantity"] == "4"
        assert rows[0]["Name"] == "Lightning Bolt"

    def test_roundtrip_archidekt(self) -> None:
        deck = _make_deck(main=[(4, "Lightning Bolt"), (2, "Counterspell")])
        exported = _svc().export_deck(deck, DeckFormat.ARCHIDEKT)
        reimported = _svc().import_deck(exported, DeckFormat.ARCHIDEKT)
        assert len(reimported.entries) == len(deck.entries)
        for orig, re_entry in zip(deck.entries, reimported.entries, strict=True):
            assert orig.card_name == re_entry.card_name
            assert orig.quantity == re_entry.quantity


# ==================================================================
# Cross-format conversion
# ==================================================================

class TestCrossFormat:
    def test_vimtg_to_arena(self) -> None:
        """Import a vimtg deck text, export as Arena format."""
        vimtg_text = "// Deck: Burn\n4 Lightning Bolt\nSB: 2 Pyroblast\n"
        deck = _svc().import_deck(vimtg_text, DeckFormat.VIMTG)
        arena_text = _svc().export_deck(deck, DeckFormat.ARENA)
        assert "Deck" in arena_text
        assert "4 Lightning Bolt" in arena_text
        assert "Sideboard" in arena_text
        assert "2 Pyroblast" in arena_text

    def test_mtgo_to_vimtg(self) -> None:
        """Import MTGO, export as vimtg native format."""
        mtgo_text = "4 Lightning Bolt\n2 Counterspell\n\nSideboard\n3 Pyroblast\n"
        deck = _svc().import_deck(mtgo_text, DeckFormat.MTGO)
        vimtg_text = _svc().export_deck(deck, DeckFormat.VIMTG)
        assert "4 Lightning Bolt" in vimtg_text
        assert "SB: 3 Pyroblast" in vimtg_text

    def test_auto_detect_and_import(self) -> None:
        """Verify auto-detect picks MTGO for plain text, then imports correctly."""
        text = "4 Lightning Bolt\n2 Counterspell\n"
        deck = _svc().import_deck(text)  # no format specified
        assert len(deck.mainboard()) == 2
        assert deck.mainboard()[0].card_name == "Lightning Bolt"

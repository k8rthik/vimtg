"""Decklist import/export fidelity — golden files per format plus
regression tests for each text-import bug the 1.0 review found.

Golden inputs live in tests/fixtures/decklists/<name>.<ext>; the
expected vimtg serialization is <name>.expected.deck. Export goldens
start from export_source.deck. Files are read as bytes and decoded so
line endings are compared exactly (Path.read_text would fold CRLF).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from vimtg.cli import main
from vimtg.data.deck_repository import DeckRepository, parse_deck_text
from vimtg.domain.card import Card, Prices, Rarity
from vimtg.domain.deck import DeckSection
from vimtg.domain.deck_lines import strip_printing_suffix
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.export_cmds import cmd_import
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor
from vimtg.services.deck_sources import SkippedLine, parse_decklist_text
from vimtg.services.import_export_service import (
    DeckFormat,
    ImportExportService,
    front_face_name,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "decklists"


def _read(name: str) -> str:
    return (FIXTURES / name).read_bytes().decode("utf-8")


def _svc() -> ImportExportService:
    return ImportExportService()


def _zones(text: str, fmt: DeckFormat | None = None) -> dict[tuple[DeckSection, str], int]:
    deck = _svc().import_deck(text, fmt)
    return {(e.section, e.card_name): e.quantity for e in deck.entries}


def _card(name: str, layout: str) -> Card:
    return Card(
        scryfall_id="id", name=name, mana_cost="", cmc=0.0, type_line="",
        oracle_text="", colors=(), color_identity=(), power=None,
        toughness=None, set_code="mh2", rarity=Rarity.COMMON,
        prices=Prices(), legalities={}, image_uri=None, layout=layout,
        keywords=(),
    )


# ==================================================================
# Golden files
# ==================================================================

IMPORT_GOLDENS = [
    ("mtgo_blank_sideboard.txt", DeckFormat.MTGO),
    ("mtgo_x_quantities.txt", DeckFormat.MTGO),
    ("arena_with_sets.txt", DeckFormat.ARENA),
    ("arena_no_sets.txt", DeckFormat.ARENA),
    ("moxfield_arena.txt", DeckFormat.ARENA),
    ("archidekt_categories.csv", DeckFormat.ARCHIDEKT),
    ("hand_edited.deck", DeckFormat.VIMTG),
]


def _expected_name(source: str) -> str:
    return source.rsplit(".", 1)[0] + ".expected.deck"


@pytest.mark.parametrize(("source", "fmt"), IMPORT_GOLDENS)
def test_import_golden(source: str, fmt: DeckFormat) -> None:
    text = _read(source)
    assert _svc().detect_format(text) in (fmt, DeckFormat.MTGO)
    for given in (None, fmt):  # auto-detected and explicit agree
        deck = _svc().import_deck(text, given)
        out = _svc().export_deck(deck, DeckFormat.VIMTG)
        assert out == _read(_expected_name(source))


@pytest.mark.parametrize(("source", "fmt"), IMPORT_GOLDENS)
def test_import_golden_survives_bom_and_crlf(source: str, fmt: DeckFormat) -> None:
    text = "﻿" + _read(source).replace("\r\n", "\n").replace("\n", "\r\n")
    deck = _svc().import_deck(text)
    out = _svc().export_deck(deck, DeckFormat.VIMTG)
    assert out == _read(_expected_name(source))


@pytest.mark.parametrize(
    ("fmt", "golden"),
    [
        (DeckFormat.ARENA, "export_source.arena.txt"),
        (DeckFormat.MTGO, "export_source.mtgo.txt"),
        (DeckFormat.ARCHIDEKT, "export_source.archidekt.csv"),
    ],
)
def test_export_golden(fmt: DeckFormat, golden: str) -> None:
    deck = _svc().import_deck(_read("export_source.deck"))
    assert _svc().export_deck(deck, fmt) == _read(golden)


# ==================================================================
# (a) MTGO blank-line sideboard
# ==================================================================

class TestMtgoBlankLineSideboard:
    def test_headerless_two_groups_split_into_sideboard(self) -> None:
        zones = _zones("4 Lightning Bolt\n20 Mountain\n\n2 Duress\n")
        assert zones[(DeckSection.MAIN, "Mountain")] == 20
        assert zones[(DeckSection.SIDEBOARD, "Duress")] == 2

    def test_trailing_and_repeated_blank_lines_are_one_divider(self) -> None:
        zones = _zones("\n4 Lightning Bolt\n\n\n2 Duress\n\n\n")
        assert zones == {
            (DeckSection.MAIN, "Lightning Bolt"): 4,
            (DeckSection.SIDEBOARD, "Duress"): 2,
        }

    def test_three_groups_are_left_in_main(self) -> None:
        # Ambiguous (a user grouping creatures/spells/lands) — no guess
        zones = _zones("4 Goblin Guide\n\n4 Lightning Bolt\n\n20 Mountain\n")
        assert all(section == DeckSection.MAIN for section, _ in zones)

    def test_explicit_header_wins_over_blank_lines(self) -> None:
        zones = _zones("4 Lightning Bolt\n\n20 Mountain\nSideboard\n2 Duress\n")
        assert zones[(DeckSection.MAIN, "Mountain")] == 20
        assert zones[(DeckSection.SIDEBOARD, "Duress")] == 2

    def test_fetchers_keep_neutral_blank_lines_by_default(self) -> None:
        remote = parse_decklist_text("4 Lightning Bolt\n\n20 Mountain\n", name="")
        assert all(e.section == DeckSection.MAIN for e in remote.deck.entries)


# ==================================================================
# (b) "4x Card" lines
# ==================================================================

class TestXQuantities:
    @pytest.mark.parametrize(
        "line", ["4x Lightning Bolt", "4X Lightning Bolt", "4 x Lightning Bolt"]
    )
    def test_x_style_line_imports(self, line: str) -> None:
        assert _zones(line + "\n", DeckFormat.MTGO) == {
            (DeckSection.MAIN, "Lightning Bolt"): 4
        }

    def test_name_starting_with_x_is_not_eaten(self) -> None:
        zones = _zones("1 Xenagos, the Reveler\n", DeckFormat.MTGO)
        assert (DeckSection.MAIN, "Xenagos, the Reveler") in zones


# ==================================================================
# (c) Arena headers without set codes
# ==================================================================

class TestArenaHeaders:
    def test_headers_without_sets_detected_as_mtgo_still_zone(self) -> None:
        text = (
            "Commander\n1 Krenko, Mob Boss\n\n"
            "Companion\n1 Lurrus of the Dream-Den\n\n"
            "Deck\n4 Lightning Bolt\n\n"
            "Sideboard\n2 Duress\n"
        )
        assert _svc().detect_format(text) == DeckFormat.MTGO
        zones = _zones(text)
        assert zones == {
            (DeckSection.COMMANDER, "Krenko, Mob Boss"): 1,
            (DeckSection.COMPANION, "Lurrus of the Dream-Den"): 1,
            (DeckSection.MAIN, "Lightning Bolt"): 4,
            (DeckSection.SIDEBOARD, "Duress"): 2,
        }

    def test_about_name_becomes_deck_name(self) -> None:
        deck = _svc().import_deck("About\nName Mono Red\n\nDeck\n4 Lightning Bolt\n")
        assert deck.metadata.name == "Mono Red"
        assert [e.card_name for e in deck.entries] == ["Lightning Bolt"]

    def test_header_with_count(self) -> None:
        zones = _zones("Deck (4)\n4 Lightning Bolt\nSideboard (2)\n2 Duress\n")
        assert zones[(DeckSection.SIDEBOARD, "Duress")] == 2


# ==================================================================
# (d) Printing suffixes
# ==================================================================

class TestPrintingSuffixes:
    @pytest.mark.parametrize(
        ("raw", "name"),
        [
            ("Goblin Guide (ZEN) 126 *F*", "Goblin Guide"),
            ("Bonecrusher Giant (PLST) ELD-115", "Bonecrusher Giant"),
            ("Sol Ring (CMM) 400a", "Sol Ring"),
            ("Arcane Signet (ELD) 331 *E*", "Arcane Signet"),
            ("Lightning Bolt (sta)", "Lightning Bolt"),
            ("Fire // Ice (MH2) 290", "Fire // Ice"),
            ("B.F.M. (Big Furry Monster)", "B.F.M. (Big Furry Monster)"),
            ("Erase (Not the Urza's Legacy One)", "Erase (Not the Urza's Legacy One)"),
        ],
    )
    def test_strip_printing_suffix(self, raw: str, name: str) -> None:
        assert strip_printing_suffix(raw) == name

    @pytest.mark.parametrize("fmt", [None, DeckFormat.MTGO, DeckFormat.ARENA])
    def test_suffixes_stripped_whatever_the_format(self, fmt: DeckFormat | None) -> None:
        text = "1 Goblin Guide (ZEN) 126 *F*\n1 Bonecrusher Giant (PLST) ELD-115\n"
        assert set(_zones(text, fmt)) == {
            (DeckSection.MAIN, "Goblin Guide"),
            (DeckSection.MAIN, "Bonecrusher Giant"),
        }

    def test_csv_name_suffix_stripped(self) -> None:
        zones = _zones("Quantity,Name\n1,Sol Ring (CMM) 400a\n", DeckFormat.ARCHIDEKT)
        assert zones == {(DeckSection.MAIN, "Sol Ring"): 1}


# ==================================================================
# (e) Archidekt CSV categories
# ==================================================================

class TestArchidektCsvCategories:
    def test_zone_categories_place_cards(self) -> None:
        text = (
            "Quantity,Name,Categories\n"
            '1,"Krenko, Mob Boss",Commander\n'
            "1,Lurrus of the Dream-Den,Companion\n"
            "4,Lightning Bolt,Burn\n"
            "2,Duress,Sideboard\n"
            "1,Opt,Maybeboard\n"
            "20,Mountain,Land\n"
        )
        deck = _svc().import_deck(text)
        placed = {(e.section, e.card_name, e.category) for e in deck.entries}
        assert placed == {
            (DeckSection.COMMANDER, "Krenko, Mob Boss", ""),
            (DeckSection.COMPANION, "Lurrus of the Dream-Den", ""),
            (DeckSection.MAIN, "Lightning Bolt", "burn"),
            (DeckSection.SIDEBOARD, "Duress", ""),
            (DeckSection.MAYBEBOARD, "Opt", ""),
            (DeckSection.MAIN, "Mountain", ""),
        }

    def test_first_category_is_primary(self) -> None:
        text = 'Quantity,Name,Categories\n1,Sol Ring,"Ramp,Sideboard"\n'
        deck = _svc().import_deck(text)
        assert (deck.entries[0].section, deck.entries[0].category) == (
            DeckSection.MAIN, "ramp",
        )

    def test_archidekt_text_bracket_categories(self) -> None:
        text = (
            "1x Krenko, Mob Boss (rvr) 112 [Commander{top}]\n"
            "4x Lightning Bolt [Burn]\n"
            "1x Opt [Maybeboard{noDeck}{noPrice}]\n"
        )
        deck = _svc().import_deck(text)
        placed = {(e.section, e.card_name, e.category) for e in deck.entries}
        assert placed == {
            (DeckSection.COMMANDER, "Krenko, Mob Boss", ""),
            (DeckSection.MAIN, "Lightning Bolt", "burn"),
            (DeckSection.MAYBEBOARD, "Opt", ""),
        }

    def test_export_round_trips_zones_and_categories(self) -> None:
        deck = _svc().import_deck(_read("export_source.deck"))
        out = _svc().export_deck(deck, DeckFormat.ARCHIDEKT)
        back = _svc().import_deck(out)
        assert {(e.section, e.card_name, e.category) for e in back.entries} == {
            (e.section, e.card_name, e.category) for e in deck.entries
        }


# ==================================================================
# (f) Skipped-line report
# ==================================================================

class TestSkippedReport:
    def test_text_import_reports_unreadable_lines(self) -> None:
        text = "4 Lightning Bolt\nthis is not a card\n0 Mountain\n// a comment\n"
        report = _svc().import_deck_report(text)
        assert report.skipped == (
            SkippedLine(2, "this is not a card"),
            SkippedLine(3, "0 Mountain"),
        )
        assert [e.card_name for e in report.deck.entries] == ["Lightning Bolt"]

    def test_headers_comments_and_groupings_are_not_reported(self) -> None:
        text = "About\nName X\nDeck\n//Lands (20)\nCreatures (4)\n# note\n4 Goblin Guide\n"
        assert _svc().import_deck_report(text).skipped == ()

    def test_vimtg_import_reports_unreadable_lines(self) -> None:
        text = "// Deck: X\n4 Lightning Bolt\nLightning Bolt\n"
        report = _svc().import_deck_report(text)
        assert report.skipped == (SkippedLine(3, "Lightning Bolt"),)

    def test_csv_rows_without_a_name_are_reported(self) -> None:
        report = _svc().import_deck_report(_read("archidekt_categories.csv"))
        assert report.skipped == (SkippedLine(8, "3,Normal,Burn"),)

    def test_moxfield_csv_rows_without_a_name_are_reported(self) -> None:
        text = "Count,Name,Section\n4,Lightning Bolt,mainboard\n2,,sideboard\n,,\n"
        report = _svc().import_deck_report(text, DeckFormat.MOXFIELD)
        assert report.skipped == (SkippedLine(3, "2,sideboard"),)
        assert [e.card_name for e in report.deck.entries] == ["Lightning Bolt"]

    def test_convert_prints_report_to_stderr(self, tmp_path: Path) -> None:
        src = tmp_path / "in.txt"
        src.write_text("4 Lightning Bolt\nnot a card\n", encoding="utf-8")
        result = CliRunner().invoke(main, ["convert", str(src), "--to", "mtgo"])
        assert result.exit_code == 0
        assert "Skipped 1 unreadable line(s)" in result.stderr
        assert "line 2: not a card" in result.stderr
        assert "not a card" not in result.stdout
        assert "4 Lightning Bolt" in result.stdout

    def test_convert_clean_input_has_empty_stderr(self, tmp_path: Path) -> None:
        src = tmp_path / "in.txt"
        src.write_text("4 Lightning Bolt\n", encoding="utf-8")
        result = CliRunner().invoke(main, ["convert", str(src), "--to", "vimtg"])
        assert result.exit_code == 0
        assert result.stderr == ""

    def test_import_command_mentions_skipped_lines(self, tmp_path: Path) -> None:
        src = tmp_path / "in.txt"
        src.write_text("4 Lightning Bolt\nnot a card\n", encoding="utf-8")
        ctx = EditorContext()
        cmd_import(
            Buffer.from_text(""), Cursor(row=0),
            ParsedCommand(name="import", args=str(src)), ctx,
        )
        assert ctx.new_buffer is not None
        assert "1 line(s) skipped (line 2: not a card)" in ctx.new_buffer.message


# ==================================================================
# (g) Hand-edited .deck files
# ==================================================================

class TestHandEditedDeck:
    def test_bom_does_not_hide_first_metadata_line(self) -> None:
        deck = parse_deck_text("﻿// Deck: Burn\n4 Lightning Bolt\n")
        assert deck.metadata.name == "Burn"

    def test_repository_load_drops_bom(self, tmp_path: Path) -> None:
        path = tmp_path / "burn.deck"
        path.write_bytes("﻿// Deck: Burn\n".encode())
        assert DeckRepository().load(path) == "// Deck: Burn\n"

    @pytest.mark.parametrize("header", ["Sideboard", "sideboard:", "SIDEBOARD"])
    def test_bare_sideboard_header(self, header: str) -> None:
        deck = parse_deck_text(f"4 Lightning Bolt\n{header}\n2 Duress\nCMD: 1 Krenko, Mob Boss\n")
        assert {(e.section, e.card_name) for e in deck.entries} == {
            (DeckSection.MAIN, "Lightning Bolt"),
            (DeckSection.SIDEBOARD, "Duress"),
            (DeckSection.COMMANDER, "Krenko, Mob Boss"),
        }

    def test_printing_suffix_stripped_keeping_tags_and_comment(self) -> None:
        deck = parse_deck_text("4 Goblin Guide (ZEN) 126 *F*  #haste  // pet card\n")
        entry = deck.entries[0]
        assert (entry.card_name, entry.tags, entry.comment) == (
            "Goblin Guide", frozenset({"haste"}), "pet card",
        )

    def test_import_merges_case_insensitive_duplicates(self) -> None:
        deck = _svc().import_deck(
            "// Deck: X\n4 Lightning Bolt  #burn\n2 lightning bolt  #spell\n"
            "SB: 1 Lightning Bolt\n"
        )
        main = [e for e in deck.entries if e.section == DeckSection.MAIN]
        assert len(main) == 1
        assert (main[0].card_name, main[0].quantity) == ("Lightning Bolt", 6)
        assert main[0].tags == frozenset({"burn", "spell"})
        side = [e for e in deck.entries if e.section == DeckSection.SIDEBOARD]
        assert [(e.card_name, e.quantity) for e in side] == [("Lightning Bolt", 1)]

    def test_duplicates_merge_in_text_formats_too(self) -> None:
        assert _zones("2 Lightning Bolt\n2 LIGHTNING BOLT\n") == {
            (DeckSection.MAIN, "Lightning Bolt"): 4
        }

    def test_different_categories_stay_separate(self) -> None:
        deck = _svc().import_deck("// Deck: X\n2 Island  @ramp\n2 island\n")
        assert len(deck.entries) == 2


# ==================================================================
# (h) Export fidelity
# ==================================================================

class TestExportNames:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Brazen Borrower // Petty Theft", "Brazen Borrower"),
            ("Delver of Secrets // Insectile Aberration", "Delver of Secrets"),
            ("Fire // Ice", "Fire"),  # no card data: front face
            ("Lightning Bolt", "Lightning Bolt"),
        ],
    )
    def test_front_face_name(self, name: str, expected: str) -> None:
        assert front_face_name(name) == expected

    def test_resolved_split_card_keeps_full_name(self) -> None:
        assert front_face_name("Fire // Ice", _card("Fire // Ice", "split")) == "Fire // Ice"
        adventure = _card("Bonecrusher Giant // Stomp", "adventure")
        assert front_face_name("Bonecrusher Giant // Stomp", adventure) == "Bonecrusher Giant"

    @pytest.mark.parametrize("fmt", [DeckFormat.ARENA, DeckFormat.MTGO, DeckFormat.MTGO_DEK])
    def test_resolved_split_card_in_exports(self, fmt: DeckFormat) -> None:
        deck = _svc().import_deck("// Deck: X\n1 Fire // Ice\n1 Brazen Borrower // Petty Theft\n")
        resolved = {"Fire // Ice": _card("Fire // Ice", "split")}
        out = _svc().export_deck(deck, fmt, resolved)
        assert "Fire // Ice" in out
        assert "Petty Theft" not in out

    def test_moxfield_keeps_full_names(self) -> None:
        deck = _svc().import_deck("// Deck: X\n1 Brazen Borrower // Petty Theft\n")
        assert "Brazen Borrower // Petty Theft" in _svc().export_deck(deck, DeckFormat.MOXFIELD)

    def test_arena_round_trip_of_front_face_export(self) -> None:
        deck = _svc().import_deck(_read("export_source.deck"))
        back = _svc().import_deck(_svc().export_deck(deck, DeckFormat.ARENA))
        assert (DeckSection.MAIN, "Brazen Borrower") in {
            (e.section, e.card_name) for e in back.entries
        }


"""Regression tests from the four-way correctness audit.

Each test pins a reproduced bug: section cleanup destroying occupied
headers, :sort corrupting zone classification, operator ranges widening
over block headers, tag round-trip growth, case-insensitive copy
limits, counted paste interleave, dot-repeat mark shifts, and
import/export zone loss.
"""

from __future__ import annotations

from vimtg.config.settings import Settings
from vimtg.data.deck_repository import parse_deck_text, serialize_deck
from vimtg.domain.validation import validate_deck
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.command_handlers.sort import cmd_sort
from vimtg.editor.commands import EditorContext, parse_command
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.modes import ModeManager
from vimtg.editor.operators import execute_operator, move_to_zone
from vimtg.editor.registers import RegisterStore
from vimtg.editor.sections import normalize_sections
from vimtg.editor.session import EditorState, handle_normal_special
from vimtg.services.history_service import HistoryService
from vimtg.services.import_export_service import DeckFormat, ImportExportService


def _state(text: str, row: int = 0) -> EditorState:
    buffer = Buffer.from_text(text)
    state = EditorState(
        buffer=buffer,
        cursor=Cursor(row=row),
        mode_mgr=ModeManager(),
        registers=RegisterStore(),
        history=HistoryService(),
        modified=False,
        resolved_cards={},
        settings=Settings(),
    )
    state.history.initialize(buffer)
    return state


def _classification_is_fresh(buf: Buffer) -> bool:
    """The in-memory line types match a from-scratch reparse."""
    reparsed = Buffer.from_text(buf.to_text())
    return all(
        buf.get_line(i).line_type is reparsed.get_line(i).line_type
        for i in range(buf.line_count())
    )


class TestSectionCleanup:
    def test_comment_between_header_and_cards_keeps_header(self):
        n = normalize_sections(
            Buffer.from_text("// Creatures\n// note to self\n4 Birds\n")
        )
        assert "// Creatures" in n.to_text()

    def test_dropping_header_never_extends_a_zone_block(self):
        n = normalize_sections(Buffer.from_text(
            "CMD:\n    1 Zur\n// Creatures\n    // note\n    1 Elves\n"
        ))
        rows = [
            i for i in range(n.line_count()) if n.card_name_at(i) == "Elves"
        ]
        assert n.get_line(rows[0]).line_type is LineType.CARD_ENTRY

    def test_terminating_header_still_dropped_when_nothing_captured(self):
        # The mc user scenario: empty type header after a CMD block
        n = normalize_sections(Buffer.from_text(
            "CMD:\n    1 Atraxa\n\n// Creature\n\n// Land\n30 Forest\n"
        ))
        assert "// Creature" not in n.to_text()
        assert "// Land" in n.to_text()


class TestSortZoneSafety:
    def test_sort_preserves_in_memory_classification(self):
        buf = Buffer.from_text("SB:\n    2 Zebra\n    1 Apple\n")
        cmd = parse_command("sort name", 1, buf.line_count())
        nb, _ = cmd_sort(buf, Cursor(row=1), cmd, EditorContext())
        assert _classification_is_fresh(nb)
        assert nb.get_line(1).line_type is LineType.SIDEBOARD_ENTRY

    def test_sort_never_moves_a_card_across_zone_boundary(self):
        buf = Buffer.from_text("CMD:\n    1 Zur the Enchanter\nSB: 1 Apple\n")
        cmd = parse_command("sort name", 1, buf.line_count())
        nb, _ = cmd_sort(buf, Cursor(row=1), cmd, EditorContext())
        deck = parse_deck_text(nb.to_text())
        assert [e.card_name for e in deck.commanders()] == ["Zur the Enchanter"]


class TestOperatorRanges:
    def test_dj_deletes_exactly_two_raw_lines(self):
        buf = Buffer.from_text("CMD:\n    1 A\n\nDCK:\n    1 B\n")
        result = execute_operator("d", "j", Cursor(row=1), buf, 1, RegisterStore())
        assert "DCK:" in result.buffer.to_text()
        assert len(result.registers.get('"').content) == 2

    def test_counted_paste_does_not_interleave(self):
        state = _state("1 Anchor\n")
        state.registers = state.registers.set_unnamed(
            ("1 First", "1 Second"), is_delete=False,
        )
        handle_normal_special(state, ParsedAction("special", "p", count=2))
        names = [
            state.buffer.card_name_at(i)
            for i in range(state.buffer.line_count())
        ]
        assert names == ["Anchor", "First", "Second", "First", "Second"]

    def test_dot_repeat_delete_shifts_marks(self):
        state = _state("1 A\n1 B\n1 C\n1 D\n", row=0)
        state.marks = state.marks.set("z", 3)
        handle_normal_special(state, ParsedAction("special", "x"))
        # After the live delete the mark sits at row 2; a dot-repeated
        # dd must shift it again, exactly like the live operator would
        from vimtg.editor.dot_repeat import RepeatableAction

        state.dot_repeat.record(RepeatableAction("operator", operator="dd", count=1))
        handle_normal_special(state, ParsedAction("special", "."))
        mark = state.marks.get("z")
        assert mark is not None and mark.row == 1


class TestZoneMoveBlockIntegrity:
    def test_move_into_foreign_block_keeps_block_intact(self):
        buf = Buffer.from_text(
            "CMD:\n    1 Zur\n    SB: 1 Wish\n    1 Tymna\n\n1 Plains\n"
        )
        result = move_to_zone(buf, Cursor(row=5), LineType.SIDEBOARD_ENTRY)
        deck = parse_deck_text(result.buffer.to_text())
        assert any(e.card_name == "Tymna" for e in deck.commanders())
        assert any(e.card_name == "Plains" for e in deck.sideboard())

    def test_move_lands_under_empty_block_header_at_eof(self):
        buf = Buffer.from_text("1 Opt\n\nSB:\n")
        result = move_to_zone(buf, Cursor(row=0), LineType.SIDEBOARD_ENTRY)
        lines = result.buffer.to_text().splitlines()
        assert lines.index("SB:") + 1 == lines.index("    1 Opt")


class TestTagRoundTrip:
    def test_invalid_suffix_round_trips_unchanged(self):
        text = "4 Cardname  #tag1 not-a-tag\n"
        once = serialize_deck(parse_deck_text(text))
        twice = serialize_deck(parse_deck_text(once))
        assert once == twice

    def test_embedded_hash_word_is_not_a_tag(self):
        deck = parse_deck_text("4 Erase #one\n")
        assert deck.entries[0].tags == frozenset()


class TestCaseInsensitiveCopies:
    def test_mixed_case_duplicates_break_singleton(self):
        deck = parse_deck_text(
            "CMD: 1 Atraxa\n1 Sol Ring\n1 sol ring\n96 Forest\n"
        )
        errors = validate_deck(deck, fmt="commander")
        assert any("copies" in e.message for e in errors)

    def test_lowercase_basics_are_exempt(self):
        deck = parse_deck_text("CMD: 1 Atraxa\n99 forest\n")
        errors = validate_deck(deck, fmt="commander")
        assert not any("copies" in e.message for e in errors)


class TestImportExportZones:
    def _deck(self):
        return parse_deck_text(
            "CMD: 1 Atraxa\nCMP: 1 Lurrus\n97 Forest\nMB: 1 Opt\n"
        )

    def test_arena_round_trips_commander_and_companion(self):
        svc = ImportExportService()
        back = svc.import_deck(
            svc.export_deck(self._deck(), DeckFormat.ARENA), DeckFormat.ARENA
        )
        assert len(back.commanders()) == 1
        assert len(back.companions()) == 1

    def test_moxfield_round_trips_commander_and_companion(self):
        svc = ImportExportService()
        back = svc.import_deck(
            svc.export_deck(self._deck(), DeckFormat.MOXFIELD),
            DeckFormat.MOXFIELD,
        )
        assert len(back.commanders()) == 1
        assert len(back.companions()) == 1

    def test_archidekt_export_excludes_maybeboard(self):
        assert "Opt" not in ImportExportService().export_deck(
            self._deck(), DeckFormat.ARCHIDEKT
        )

    def test_mtgo_export_parks_commander_in_sideboard(self):
        out = ImportExportService().export_deck(self._deck(), DeckFormat.MTGO)
        assert "Atraxa" in out.split("Sideboard")[1]

    def test_native_zone_lines_detect_as_vimtg(self):
        svc = ImportExportService()
        assert svc.detect_format("4 Bolt\nSB: 2 Duress\n") is DeckFormat.VIMTG
        back = svc.import_deck("4 Bolt\nSB: 2 Duress\nCMD: 1 Atraxa\n")
        assert len(back.sideboard()) == 1
        assert len(back.commanders()) == 1

    def test_importer_quantities_are_clamped(self):
        svc = ImportExportService()
        deck = svc.import_deck("999999999 Mountain\n", DeckFormat.MTGO)
        assert deck.entries[0].quantity == 999


class TestSideboardPlanExport:
    _DECK = (
        "// Deck: Burn\n4 Bolt\nSB: 3 Alpine Moon\n\n"
        "VS: Tron\n    -4 Bolt\n    +3 Alpine Moon\n"
    )

    def _deck(self):
        return parse_deck_text(self._DECK)

    def test_foreign_formats_drop_plans(self):
        svc = ImportExportService()
        for fmt in (
            DeckFormat.ARENA, DeckFormat.MTGO, DeckFormat.MTGO_DEK,
            DeckFormat.MOXFIELD, DeckFormat.ARCHIDEKT,
        ):
            out = svc.export_deck(self._deck(), fmt)
            assert "VS:" not in out and "Tron" not in out, fmt

    def test_vimtg_export_keeps_plans(self):
        out = ImportExportService().export_deck(self._deck(), DeckFormat.VIMTG)
        assert "VS: Tron\n    -4 Bolt\n    +3 Alpine Moon\n" in out

    def test_guide_export_is_markdown(self):
        out = ImportExportService().export_deck(self._deck(), DeckFormat.GUIDE)
        assert out.startswith("# Burn — sideboard guide\n")
        assert "## vs Tron\n- OUT: 4 Bolt\n- IN: 3 Alpine Moon\n" in out

    def test_guide_is_export_only(self):
        import pytest

        with pytest.raises(ValueError, match="export-only"):
            ImportExportService().import_deck("# x", DeckFormat.GUIDE)

    def test_plan_only_marker_detects_as_vimtg(self):
        text = "4 Bolt\n\nVS: Tron\n    -4 Bolt\n"
        assert ImportExportService().detect_format(text) is DeckFormat.VIMTG
        assert len(ImportExportService().import_deck(text).plans) == 1

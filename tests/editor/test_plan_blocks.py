"""Sideboard-plan blocks in the editor buffer: classification, accessors,
and the buffer-rewriting passes (cleanup, layout, sort) that must leave
them alone."""

from __future__ import annotations

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer, LineType, insertion_zone
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry, EditorContext, parse_command
from vimtg.editor.cursor import Cursor
from vimtg.editor.layout import regroup_buffer
from vimtg.editor.motions import (
    motion_section_header_next,
    motion_section_header_prev,
)
from vimtg.editor.operators import decrement_quantity, increment_quantity
from vimtg.editor.sections import matched_indent, normalize_sections

DECK = (
    "// Deck: Burn\n"
    "\n"
    "DCK:\n"
    "    // Instant\n"
    "    4 Lightning Bolt\n"
    "    2 Skullcrack\n"
    "\n"
    "SB:\n"
    "    3 Alpine Moon\n"
    "    2 Skullcrack\n"
    "\n"
    "VS: Tron\n"
    "    -4 Lightning Bolt\n"
    "    +3 Alpine Moon  // hoses their lands\n"
    "    2 Skullcrack\n"
    "\n"
    "VS: Burn\n"
    "    -2 Skullcrack\n"
)
PLAN_TEXT = DECK[DECK.index("VS: Tron"):]


class TestClassification:
    def test_header_and_entries(self) -> None:
        buf = Buffer.from_text(DECK)
        assert buf.get_line(11).line_type is LineType.PLAN_HEADER
        assert buf.get_line(12).line_type is LineType.PLAN_ENTRY
        assert buf.get_line(13).line_type is LineType.PLAN_ENTRY

    def test_unsigned_line_in_a_plan_is_a_plan_entry_not_a_card(self) -> None:
        buf = Buffer.from_text(DECK)
        assert buf.get_line(14).line_type is LineType.PLAN_ENTRY
        assert not buf.is_card_line(14)

    def test_signed_line_outside_a_plan_is_a_comment(self) -> None:
        buf = Buffer.from_text("4 Opt\n+2 Duress\n")
        assert buf.get_line(1).line_type is LineType.COMMENT

    def test_plan_header_closes_a_zone_block(self) -> None:
        buf = Buffer.from_text("SB:\n    2 Duress\nVS: x\n    2 Duress\n")
        assert buf.get_line(1).line_type is LineType.SIDEBOARD_ENTRY
        assert buf.get_line(3).line_type is LineType.PLAN_ENTRY

    def test_explicit_prefix_wins_inside_a_plan(self) -> None:
        buf = Buffer.from_text("VS: x\n    SB: 1 Duress\n")
        assert buf.get_line(1).line_type is LineType.SIDEBOARD_ENTRY

    def test_bare_vs_is_not_a_header(self) -> None:
        buf = Buffer.from_text("VS:\n    -1 Opt\n")
        assert buf.get_line(0).line_type is LineType.COMMENT
        assert buf.get_line(1).line_type is LineType.COMMENT


class TestIncrementalEdits:
    def _fresh(self, buf: Buffer) -> bool:
        again = Buffer.from_text(buf.to_text())
        return all(
            buf.get_line(i).line_type is again.get_line(i).line_type
            for i in range(buf.line_count())
        )

    def test_set_line_inside_a_plan(self) -> None:
        buf = Buffer.from_text(DECK).set_line(12, "    -2 Lightning Bolt")
        assert buf.get_line(12).line_type is LineType.PLAN_ENTRY
        assert self._fresh(buf)

    def test_insert_line_inside_a_plan(self) -> None:
        buf = Buffer.from_text(DECK).insert_line(13, "    +1 Skullcrack")
        assert buf.get_line(13).line_type is LineType.PLAN_ENTRY
        assert self._fresh(buf)

    def test_deleting_the_header_reclassifies_its_entries(self) -> None:
        buf, _ = Buffer.from_text("4 Opt\nVS: x\n    -1 Opt\n").delete_lines(1, 1)
        assert buf.get_line(1).line_type is LineType.COMMENT
        assert self._fresh(buf)

    def test_turning_a_comment_into_a_header_reclassifies_below(self) -> None:
        buf = Buffer.from_text("// x\n    -1 Opt\n").set_line(0, "VS: x")
        assert buf.get_line(1).line_type is LineType.PLAN_ENTRY
        assert self._fresh(buf)

    def test_insertion_zone_inside_a_plan(self) -> None:
        buf = Buffer.from_text(DECK)
        assert insertion_zone(buf, 13) is LineType.PLAN_ENTRY
        assert insertion_zone(buf, 5) is LineType.CARD_ENTRY


class TestAccessors:
    def test_card_name_and_quantity(self) -> None:
        buf = Buffer.from_text(DECK)
        assert buf.card_name_at(12) == "Lightning Bolt"
        assert buf.quantity_at(12) == 4
        assert buf.card_name_at(13) == "Alpine Moon"
        assert buf.comment_at(13) == "hoses their lands"
        assert buf.plan_sign_at(12) == "-"
        assert buf.plan_sign_at(13) == "+"
        assert buf.plan_sign_at(14) == ""
        assert buf.plan_sign_at(11) is None

    def test_set_quantity_keeps_the_sign(self) -> None:
        buf = Buffer.from_text(DECK).set_quantity(12, 2)
        assert buf.get_line(12).text == "    -2 Lightning Bolt"
        buf = buf.set_quantity(13, 1)
        assert buf.get_line(13).text == "    +1 Alpine Moon  // hoses their lands"

    def test_plus_minus_keys_adjust_a_plan_entry(self) -> None:
        buf = Buffer.from_text(DECK)
        buf = increment_quantity(buf, Cursor(row=13), 1)
        assert buf.get_line(13).text.startswith("    +4 Alpine Moon")
        buf, cursor = decrement_quantity(buf, Cursor(row=12), 4)
        assert buf.get_line(12).text.startswith("    +4 Alpine Moon")  # line deleted
        assert cursor.row == 12


class TestRewritePasses:
    def test_cleanup_keeps_an_empty_plan(self) -> None:
        buf = Buffer.from_text("4 Opt\n\nVS: Tron\n")
        assert normalize_sections(buf) is buf

    def test_cleanup_pads_before_a_plan_header(self) -> None:
        buf = normalize_sections(Buffer.from_text("4 Opt\nVS: Tron\n    -1 Opt\n"))
        assert buf.to_text() == "4 Opt\n\nVS: Tron\n    -1 Opt\n"

    def test_cleanup_leaves_plans_byte_identical(self) -> None:
        buf = normalize_sections(Buffer.from_text(DECK))
        assert buf.to_text().endswith(PLAN_TEXT)

    def test_layout_regroup_carries_plans_verbatim(self) -> None:
        for mode in ("type", "category"):
            out = regroup_buffer(Buffer.from_text(DECK), mode)
            assert out.to_text().endswith(PLAN_TEXT), mode
            assert out.to_text().count("VS: ") == 2
            assert [
                out.get_line(i).line_type for i in range(out.line_count())
            ].count(LineType.CARD_ENTRY) == 2

    def test_sort_leaves_plan_lines_alone(self) -> None:
        registry = CommandRegistry()
        register_all_commands(registry)
        buf = Buffer.from_text(DECK)
        ctx = EditorContext(settings=Settings())
        cmd = parse_command("%sort name", 0, buf.line_count())
        out, _ = registry.execute(cmd, buf, Cursor(), ctx)
        assert out.to_text().endswith(PLAN_TEXT)

    def test_matched_indent_under_a_plan_header(self) -> None:
        buf = Buffer.from_text("VS: Tron\n")
        assert matched_indent(buf, 1) == "    "


class TestMotions:
    def test_bracket_motions_stop_on_plan_headers(self) -> None:
        buf = Buffer.from_text(DECK)
        c = motion_section_header_next(Cursor(row=8), buf)
        assert c.row == 11
        c = motion_section_header_next(c, buf)
        assert c.row == 16
        c = motion_section_header_prev(c, buf)
        assert c.row == 11


class TestZoneMovesAroundPlans:
    def test_ms_lands_in_the_sideboard_block_not_the_plan(self) -> None:
        from vimtg.editor.operators import move_to_zone

        buf = Buffer.from_text(DECK)
        r = move_to_zone(buf, Cursor(row=5), LineType.SIDEBOARD_ENTRY, 0)
        text = r.buffer.to_text()
        assert text.endswith(PLAN_TEXT)
        assert r.buffer.get_line(r.cursor.row).line_type is LineType.SIDEBOARD_ENTRY

    def test_md_from_the_sideboard_keeps_the_plan_intact(self) -> None:
        from vimtg.editor.operators import move_to_zone

        buf = Buffer.from_text(DECK)
        r = move_to_zone(buf, Cursor(row=8), LineType.CARD_ENTRY, 0)
        assert r.buffer.to_text().endswith(PLAN_TEXT)

    def test_ms_into_a_deck_whose_only_block_after_main_is_a_plan(self) -> None:
        from vimtg.editor.operators import move_to_zone

        buf = Buffer.from_text("DCK:\n    4 Opt\n\nVS: Tron\n    -1 Opt\n")
        r = move_to_zone(buf, Cursor(row=1), LineType.SIDEBOARD_ENTRY, 0)
        assert r.moved
        out = r.buffer.to_text()
        assert "VS: Tron\n    -1 Opt\n" in out
        assert r.buffer.get_line(r.inserted_row or 0).line_type is LineType.SIDEBOARD_ENTRY
        assert Buffer.from_text(out).get_line(r.inserted_row or 0).line_type is (
            LineType.SIDEBOARD_ENTRY
        )

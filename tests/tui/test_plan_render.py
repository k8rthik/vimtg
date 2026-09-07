"""Rendering of sideboard plans: VS: headers with -x +y counts, signed
plan entries, delta cells on deck cards, and the status-line segment."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.header_counts import HeaderCount, header_counts
from vimtg.tui.deck_renderer import render_line
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.status_line import StatusLine

from .test_deck_renderer import _make_card

DECK = (
    "DCK:\n"
    "    4 Lightning Bolt\n"   # 1
    "\n"
    "SB:\n"
    "    3 Rest in Peace\n"    # 4
    "\n"
    "VS: Tron\n"               # 6
    "    -4 Lightning Bolt\n"  # 7
    "    +3 Rest in Peace  // graveyard hate\n"  # 8
    "    2 Opt\n"              # 9
    "\n"
    "VS: Empty\n"              # 11
)


def _styles_at(text, label: str) -> str:
    start = text.plain.index(label)
    return " ".join(
        str(span.style) for span in text.spans if span.start <= start < span.end
    )


class TestHeaderCounts:
    def test_plan_header_carries_outs_and_ins(self) -> None:
        counts = header_counts(Buffer.from_text(DECK))
        assert counts[6] == HeaderCount(main=0, outs=4, ins=3, plan=True)

    def test_empty_plan_is_still_annotated(self) -> None:
        counts = header_counts(Buffer.from_text(DECK))
        assert counts[11] == HeaderCount(main=0, outs=0, ins=0, plan=True)

    def test_deck_title_ignores_plan_lines(self) -> None:
        buf = Buffer.from_text("// Deck: x\n" + DECK)
        assert header_counts(buf)[0] == HeaderCount(main=4, side=3)


class TestPlanHeaderRender:
    def test_shows_name_and_totals(self) -> None:
        buf = Buffer.from_text(DECK)
        counts = header_counts(buf)
        line = render_line(6, buf, 0, {}, header_count=counts[6])[0]
        assert "VS: Tron" in line.plain
        assert "(-4 +3)" in line.plain
        assert "!" in line.plain

    def test_balanced_plan_has_no_mark(self) -> None:
        buf = Buffer.from_text("4 Opt\nSB: 4 Duress\nVS: x\n    -4 Opt\n    +4 Duress\n")
        counts = header_counts(buf)
        line = render_line(2, buf, 0, {}, header_count=counts[2])[0]
        assert "(-4 +4)" in line.plain
        assert "!" not in line.plain


class TestPlanEntryRender:
    def test_out_entry(self) -> None:
        buf = Buffer.from_text(DECK)
        line = render_line(7, buf, 0, {})[0]
        assert "-4" in line.plain
        assert "Lightning Bolt" in line.plain
        assert COLORS["error"] in _styles_at(line, "-4")

    def test_in_entry_with_card_data_and_comment(self) -> None:
        buf = Buffer.from_text(DECK)
        card = _make_card(name="Rest in Peace", mana_cost="{1}{W}", type_line="Enchantment")
        line = render_line(8, buf, 0, {"Rest in Peace": card})[0]
        assert "+3" in line.plain
        assert "{1}{W}" in line.plain
        assert "Enchantment" in line.plain
        assert "// graveyard hate" in line.plain
        assert COLORS["success"] in _styles_at(line, "+3")

    def test_unsigned_entry_is_flagged_visually(self) -> None:
        buf = Buffer.from_text(DECK)
        line = render_line(9, buf, 0, {})[0]
        assert "?2" in line.plain
        assert "Opt" in line.plain

    def test_cursor_on_entry_expands_card(self) -> None:
        buf = Buffer.from_text(DECK)
        card = _make_card()
        lines = render_line(7, buf, 7, {"Lightning Bolt": card})
        assert len(lines) > 1
        assert "3 damage" in lines[2].plain


class TestDeltaCell:
    def test_out_delta_on_a_main_card(self) -> None:
        buf = Buffer.from_text(DECK)
        line = render_line(1, buf, 0, {}, plan_delta=-4)[0]
        assert line.plain.rstrip().endswith("-4")
        assert COLORS["error"] in _styles_at(line, "-4")

    def test_in_delta_on_a_side_card(self) -> None:
        buf = Buffer.from_text(DECK)
        card = _make_card(name="Rest in Peace", type_line="Enchantment")
        line = render_line(4, buf, 0, {"Rest in Peace": card}, plan_delta=3)[0]
        assert "+3" in line.plain
        assert COLORS["success"] in _styles_at(line, "+3")

    def test_no_delta_by_default(self) -> None:
        buf = Buffer.from_text(DECK)
        line = render_line(1, buf, 0, {})[0]
        assert "-4" not in line.plain


class TestStatusLine:
    def test_plan_segment(self) -> None:
        sl = StatusLine()
        sl.plan_status = "vs Tron -4/+3"
        sl.plan_unbalanced = True
        text = sl.render()
        assert "vs Tron -4/+3 !" in text.plain
        assert COLORS["sideboard"] in _styles_at(text, "vs Tron")

    def test_no_plan_segment_when_inactive(self) -> None:
        text = StatusLine().render()
        assert "vs " not in text.plain

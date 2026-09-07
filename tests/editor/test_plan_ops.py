"""Tests for editor.plan_ops — the pure boarding edits behind mi/mo and :plan."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.plan_ops import (
    board,
    ensure_plan,
    find_block,
    next_plan_row,
    plan_blocks,
    plan_summary,
)

DECK = (
    "DCK:\n"
    "    4 Lightning Bolt\n"  # 1
    "    2 Skullcrack\n"      # 2
    "\n"
    "SB:\n"
    "    3 Alpine Moon\n"     # 5
    "    2 Skullcrack\n"      # 6
    "\n"
    "VS: Tron\n"              # 8
    "    -2 Lightning Bolt\n"  # 9
    "    +1 Alpine Moon\n"     # 10
    "\n"
    "VS: Burn\n"              # 12
)


class TestBlocks:
    def test_plan_blocks(self) -> None:
        blocks = plan_blocks(Buffer.from_text(DECK))
        assert [(b.name, b.header_row, b.entry_rows) for b in blocks] == [
            ("Tron", 8, (9, 10)),
            ("Burn", 12, ()),
        ]

    def test_find_block_case_insensitive(self) -> None:
        buf = Buffer.from_text(DECK)
        assert find_block(buf, "tron").header_row == 8
        assert find_block(buf, "Mirror") is None

    def test_plan_summary(self) -> None:
        buf = Buffer.from_text(DECK)
        assert plan_summary(buf, find_block(buf, "Tron")) == "-2 +1"

    def test_next_plan_row(self) -> None:
        buf = Buffer.from_text(DECK)
        assert next_plan_row(buf, 0, forward=True) == 8
        assert next_plan_row(buf, 8, forward=True) == 12
        assert next_plan_row(buf, 12, forward=True) is None
        assert next_plan_row(buf, 12, forward=False) == 8
        assert next_plan_row(buf, 8, forward=False) is None


class TestEnsurePlan:
    def test_existing_plan_is_found(self) -> None:
        buf = Buffer.from_text(DECK)
        out, row, created = ensure_plan(buf, "tron")
        assert out is buf
        assert row == 8
        assert created is False

    def test_new_plan_is_appended_normalize_stable(self) -> None:
        buf = Buffer.from_text("4 Opt\n")
        out, row, created = ensure_plan(buf, "Mirror")
        assert created is True
        assert out.to_text() == "4 Opt\n\nVS: Mirror\n"
        assert row == 2

    def test_new_plan_after_existing_plans(self) -> None:
        out, row, _ = ensure_plan(Buffer.from_text(DECK), "Mirror")
        assert out.to_text().endswith("VS: Burn\n\nVS: Mirror\n")
        assert out.get_line(row).text == "VS: Mirror"


class TestBoardOut:
    def test_out_creates_an_entry(self) -> None:
        r = board(Buffer.from_text(DECK), row=2, plan="Tron", direction="out", count=0)
        assert not r.error
        assert r.buffer.get_line(10).text == "    -2 Skullcrack"  # after the outs
        assert r.buffer.get_line(11).text == "    +1 Alpine Moon"
        assert r.message == "vs Tron: -2 Skullcrack  (-4 +1)"
        assert r.inserted_row == 10

    def test_out_increments_an_existing_entry(self) -> None:
        r = board(Buffer.from_text(DECK), row=1, plan="Tron", direction="out", count=1)
        assert r.buffer.get_line(9).text == "    -3 Lightning Bolt"
        assert r.inserted_row is None

    def test_out_is_clamped_to_the_copies_in_the_deck(self) -> None:
        r = board(Buffer.from_text(DECK), row=1, plan="Tron", direction="out", count=9)
        assert r.buffer.get_line(9).text == "    -4 Lightning Bolt"

    def test_out_with_nothing_left_to_board(self) -> None:
        buf = board(Buffer.from_text(DECK), row=1, plan="Tron", direction="out", count=0).buffer
        r = board(buf, row=1, plan="Tron", direction="out", count=0)
        assert r.buffer is buf
        assert "already" in r.message

    def test_in_on_a_main_card_brings_it_back(self) -> None:
        r = board(Buffer.from_text(DECK), row=1, plan="Tron", direction="in", count=1)
        assert r.buffer.get_line(9).text == "    -1 Lightning Bolt"
        r = board(r.buffer, row=1, plan="Tron", direction="in", count=0)
        assert r.buffer.get_line(9).text == "    +1 Alpine Moon"  # entry removed
        assert r.deleted_row == 9

    def test_in_on_a_main_card_not_boarded_out(self) -> None:
        r = board(Buffer.from_text(DECK), row=2, plan="Tron", direction="in", count=0)
        assert r.error
        assert "not boarded out" in r.message


class TestBoardIn:
    def test_in_creates_an_entry_at_the_end(self) -> None:
        r = board(Buffer.from_text(DECK), row=6, plan="Tron", direction="in", count=0)
        assert r.buffer.get_line(11).text == "    +2 Skullcrack"
        assert r.message == "vs Tron: +2 Skullcrack  (-2 +3)"

    def test_in_increments_and_clamps(self) -> None:
        r = board(Buffer.from_text(DECK), row=5, plan="Tron", direction="in", count=5)
        assert r.buffer.get_line(10).text == "    +3 Alpine Moon"

    def test_out_on_a_side_card_takes_it_back_out(self) -> None:
        r = board(Buffer.from_text(DECK), row=5, plan="Tron", direction="out", count=0)
        assert r.buffer.get_line(9).text == "    -2 Lightning Bolt"
        assert r.buffer.line_count() == Buffer.from_text(DECK).line_count() - 1

    def test_first_entry_in_an_empty_plan(self) -> None:
        r = board(Buffer.from_text(DECK), row=5, plan="Burn", direction="in", count=2)
        assert r.buffer.get_line(13).text == "    +2 Alpine Moon"
        assert r.message == "vs Burn: +2 Alpine Moon  (-0 +2)"


class TestBoardErrors:
    def test_needs_a_deck_card(self) -> None:
        r = board(Buffer.from_text(DECK), row=9, plan="Tron", direction="out", count=0)
        assert r.error
        r = board(Buffer.from_text(DECK), row=0, plan="Tron", direction="out", count=0)
        assert r.error

    def test_unknown_plan(self) -> None:
        r = board(Buffer.from_text(DECK), row=1, plan="Mirror", direction="out", count=0)
        assert r.error
        assert "Mirror" in r.message

    def test_same_card_in_both_zones_is_keyed_by_the_cursor_line(self) -> None:
        buf = Buffer.from_text(DECK)
        out = board(buf, row=2, plan="Tron", direction="out", count=0).buffer
        r = board(out, row=6, plan="Tron", direction="in", count=1)
        texts = [r.buffer.get_line(i).text for i in range(r.buffer.line_count())]
        assert "    -2 Skullcrack" in texts
        assert "    +1 Skullcrack" in texts


class TestRowDeltas:
    def test_deltas_land_on_the_deck_rows(self) -> None:
        from vimtg.editor.plan_ops import row_deltas

        buf = Buffer.from_text(DECK)
        assert row_deltas(buf, "Tron") == {1: -2, 5: 1}

    def test_same_card_in_both_zones(self) -> None:
        from vimtg.editor.plan_ops import row_deltas

        buf = Buffer.from_text(DECK)
        buf = board(buf, row=2, plan="Tron", direction="out", count=0).buffer
        buf = board(buf, row=6, plan="Tron", direction="in", count=1).buffer
        deltas = row_deltas(buf, "Tron")
        assert deltas[2] == -2
        assert deltas[6] == 1

    def test_unknown_plan_is_empty(self) -> None:
        from vimtg.editor.plan_ops import row_deltas

        assert row_deltas(Buffer.from_text(DECK), "Mirror") == {}


class TestPlanSearch:
    def test_candidates_come_from_the_deck(self) -> None:
        from vimtg.editor.plan_ops import plan_search

        buf = Buffer.from_text(DECK)
        names = [c.name for c in plan_search(buf, {}, "sk")]
        assert names == ["Skullcrack"]  # one result per name, not per zone
        names = [c.name for c in plan_search(buf, {}, "al")]
        assert names == ["Alpine Moon"]

    def test_sideboard_cards_rank_first(self) -> None:
        from vimtg.editor.plan_ops import plan_search

        buf = Buffer.from_text(DECK)
        names = [c.name for c in plan_search(buf, {}, "l")]
        assert names.index("Alpine Moon") < names.index("Lightning Bolt")

    def test_resolved_cards_are_used_when_available(self) -> None:
        from vimtg.domain.card import Card
        from vimtg.editor.plan_ops import plan_search

        card = Card.from_scryfall({"id": "x", "name": "Alpine Moon", "mana_cost": "{R}"})
        buf = Buffer.from_text(DECK)
        found = plan_search(buf, {"Alpine Moon": card}, "alpine")
        assert found[0] is card

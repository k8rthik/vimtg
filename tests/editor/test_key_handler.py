"""Unit tests for the key_handler dispatch functions.

These exercise the pure-ish handlers directly by constructing an EditorState,
covering motions, operators, mode switches, normal-mode specials, ex-command
execution, tag actions, dot-repeat, macros, and the insert/command/tag input
sub-mode handlers.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_completer import CommandCompleter
from vimtg.editor.command_handlers.buffer_cmds import register_buffer_commands
from vimtg.editor.commands import CommandRegistry
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import (
    EditorState,
    InsertSubmode,
    count_cards,
    handle_command,
    handle_command_special,
    handle_insert_special,
    handle_mode_switch,
    handle_motion,
    handle_normal_special,
    handle_operator,
    handle_tag_input_special,
    resolve_cards,
)
from vimtg.services.history_service import HistoryService

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

DECK = "// Creatures\n4 Goblin Guide\n4 Monastery Swiftspear\n2 Eidolon of the Great Revel\n"


def _state(text: str = DECK, row: int = 1) -> EditorState:
    buf = Buffer.from_text(text)
    history = HistoryService()
    history.initialize(buf)
    return EditorState(
        buffer=buf,
        cursor=Cursor(row=row),
        mode_mgr=ModeManager(),
        registers=RegisterStore(),
        history=history,
        modified=False,
        resolved_cards={},
    )


def _act(action: str, *, action_type: str = "special", **kw) -> ParsedAction:
    return ParsedAction(action_type=action_type, action=action, **kw)


# ── handle_motion ──────────────────────────────────────────────────


class TestHandleMotion:
    def test_motion_j_moves_down(self) -> None:
        st = _state(row=0)
        handle_motion(st, _act("j", action_type="motion"))
        assert st.cursor.row == 1

    def test_g_bare_goes_last(self) -> None:
        st = _state(row=0)
        handle_motion(st, _act("G", action_type="motion", count=1))
        assert st.cursor.row == st.buffer.line_count() - 1

    def test_g_with_count_goes_to_line(self) -> None:
        # Regression: 5G must jump to line 5, not the last line.
        st = _state("a\nb\nc\nd\ne\nf\n", row=0)
        handle_motion(st, _act("G", action_type="motion", count=3))
        assert st.cursor.row == 2  # 1-indexed line 3 -> row 2

    def test_g_count_clamped_to_last(self) -> None:
        st = _state("a\nb\nc\n", row=0)
        handle_motion(st, _act("G", action_type="motion", count=99))
        assert st.cursor.row == 2

    def test_unknown_motion_noop(self) -> None:
        st = _state(row=1)
        handle_motion(st, _act("zzz", action_type="motion"))
        assert st.cursor.row == 1


# ── handle_operator ────────────────────────────────────────────────


class TestHandleOperator:
    def test_dd_deletes_line(self) -> None:
        st = _state(row=1)
        before = st.buffer.line_count()
        handle_operator(st, _act("dd", action_type="operator"))
        assert st.buffer.line_count() == before - 1
        assert st.modified is True

    def test_visual_operator_deletes_range(self) -> None:
        st = _state(row=1)
        st.visual_anchor = 2  # rows 1..2
        st.mode_mgr.transition(Mode.VISUAL_LINE)
        hr = handle_operator(st, _act("d", action_type="operator"))
        assert hr.exit_to_normal is True
        assert st.visual_anchor is None


# ── handle_mode_switch ─────────────────────────────────────────────


class TestHandleModeSwitch:
    def test_escape_exits_to_normal(self) -> None:
        st = _state()
        st.visual_anchor = 0
        hr = handle_mode_switch(st, _act("escape", action_type="mode_switch"))
        assert hr.exit_to_normal is True
        assert st.visual_anchor is None

    def test_o_opens_line_below(self) -> None:
        st = _state(row=1)
        hr = handle_mode_switch(st, _act("o", action_type="mode_switch"))
        assert hr.enter_insert is True
        assert st.cursor.row == 2

    def test_o_upper_opens_line_above(self) -> None:
        st = _state(row=1)
        hr = handle_mode_switch(st, _act("O", action_type="mode_switch"))
        assert hr.enter_insert is True

    def test_colon_enters_command(self) -> None:
        st = _state()
        assert handle_mode_switch(st, _act(":", action_type="mode_switch")).enter_command

    def test_slash_enters_search(self) -> None:
        st = _state()
        assert handle_mode_switch(st, _act("/", action_type="mode_switch")).enter_search

    def test_v_enters_visual(self) -> None:
        st = _state(row=1)
        hr = handle_mode_switch(st, _act("v", action_type="mode_switch"))
        assert hr.enter_visual == Mode.VISUAL
        assert st.visual_anchor == 1

    def test_v_upper_enters_visual_line(self) -> None:
        st = _state(row=1)
        hr = handle_mode_switch(st, _act("V", action_type="mode_switch"))
        assert hr.enter_visual == Mode.VISUAL_LINE


# ── handle_normal_special ──────────────────────────────────────────


class TestNormalSpecial:
    def test_increment_quantity(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("+"))
        assert st.buffer.quantity_at(1) == 5
        assert st.modified is True

    def test_decrement_quantity(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("-"))
        assert st.buffer.quantity_at(1) == 3

    def test_x_deletes_card_line(self) -> None:
        st = _state(row=1)
        before = st.buffer.line_count()
        handle_normal_special(st, _act("x"))
        assert st.buffer.line_count() == before - 1

    def test_undo_redo(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("+"))  # mutate + record
        handle_normal_special(st, _act("u"))
        assert st.buffer.quantity_at(1) == 4
        handle_normal_special(st, _act("ctrl_r"))
        assert st.buffer.quantity_at(1) == 5

    def test_put_after_delete(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("x"))  # yanks to unnamed register
        before = st.buffer.line_count()
        handle_normal_special(st, _act("p"))
        assert st.buffer.line_count() == before + 1

    def test_put_above(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("x"))
        before = st.buffer.line_count()
        handle_normal_special(st, _act("P"))
        assert st.buffer.line_count() == before + 1

    def test_help_requested(self) -> None:
        assert handle_normal_special(_state(), _act("?")).help_requested is True

    def test_set_mark_and_jump(self) -> None:
        st = _state(row=2)
        hr = handle_normal_special(st, _act("ma"))
        assert "Mark 'a' set" in hr.command_message
        st.cursor = st.cursor.move_to(0, 0)
        handle_normal_special(st, _act("'a"))
        assert st.cursor.row == 2

    def test_jump_to_unset_mark(self) -> None:
        st = _state()
        hr = handle_normal_special(st, _act("'z"))
        assert "not set" in hr.command_message

    def test_dot_repeat_quantity(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("+"))  # records dot
        st.cursor = st.cursor.move_to(2, 0)
        handle_normal_special(st, _act("."))
        assert st.buffer.quantity_at(2) == 5


# ── count prefixes on normal-mode specials (10+, 2x, 3p, …) ────────


class TestCountedSpecials:
    def test_counted_increment(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("+", count=10))
        assert st.buffer.quantity_at(1) == 14

    def test_counted_decrement(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("-", count=3))
        assert st.buffer.quantity_at(1) == 1

    def test_counted_decrement_past_zero_deletes_line(self) -> None:
        st = _state(row=1)
        before = st.buffer.line_count()
        handle_normal_special(st, _act("-", count=4))
        assert st.buffer.line_count() == before - 1

    def test_counted_x_deletes_multiple_cards(self) -> None:
        st = _state(row=1)
        before = st.buffer.line_count()
        handle_normal_special(st, _act("x", count=2))
        assert st.buffer.line_count() == before - 2

    def test_counted_put_pastes_multiple_copies(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("x"))  # yanks to unnamed register
        before = st.buffer.line_count()
        handle_normal_special(st, _act("p", count=3))
        assert st.buffer.line_count() == before + 3

    def test_counted_undo_redo(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("+"))
        handle_normal_special(st, _act("+"))
        handle_normal_special(st, _act("u", count=2))
        assert st.buffer.quantity_at(1) == 4
        handle_normal_special(st, _act("ctrl_r", count=2))
        assert st.buffer.quantity_at(1) == 6

    def test_counted_undo_stops_at_history_start(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("+"))
        handle_normal_special(st, _act("u", count=99))
        assert st.buffer.quantity_at(1) == 4

    def test_dot_repeats_counted_quantity(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("+", count=5))
        st.cursor = st.cursor.move_to(2, 0)
        handle_normal_special(st, _act("."))
        assert st.buffer.quantity_at(2) == 9  # 4 + 5

    def test_counted_dot_overrides_recorded_count(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("+"))  # 4 -> 5, records count=1
        handle_normal_special(st, _act(".", count=3))  # 5 -> 8
        assert st.buffer.quantity_at(1) == 8

    def test_dot_repeats_counted_x(self) -> None:
        st = _state(row=1)
        handle_normal_special(st, _act("x", count=2))
        st.buffer = Buffer.from_text(DECK)
        st.cursor = st.cursor.move_to(1, 0)
        handle_normal_special(st, _act("."))
        assert st.buffer.line_count() == Buffer.from_text(DECK).line_count() - 2

    def test_counted_macro_replay(self) -> None:
        st = _state(row=1)
        st.macros.start_recording("a")
        st.macros.record_key("+")
        st.macros.stop_recording()
        hr = handle_normal_special(st, _act("@a", count=3))
        assert hr.replay_keys == ("+", "+", "+")


# ── tag actions via normal special (t<x>) ──────────────────────────


class TestTagActions:
    def test_tag_list_empty(self) -> None:
        st = _state()
        hr = handle_normal_special(st, _act("tl"))
        assert "No tags" in hr.command_message

    def test_tag_clear_no_tags(self) -> None:
        st = _state(row=1)
        hr = handle_normal_special(st, _act("tc"))
        assert "No tags to clear" in hr.command_message

    def test_tag_input_enter_prompt(self) -> None:
        st = _state(row=1)
        hr = handle_normal_special(st, _act("ta"))
        assert hr.enter_tag_input is True
        assert st.insert_submode == InsertSubmode.TAG_INPUT

    def test_jump_to_tagged_no_tags(self) -> None:
        st = _state(row=1)
        hr = handle_normal_special(st, _act("tn"))
        assert "No tags on current card" in hr.command_message


# ── handle_tag_input_special / _apply_tag_input ────────────────────


class TestTagInput:
    def test_add_tag_via_input(self) -> None:
        st = _state(row=1)
        st.tag_input_action = "a"
        hr = handle_tag_input_special(st, _act("enter", text="core"))
        assert hr.exit_to_normal is True
        assert "core" in st.buffer.tags_at(1)
        assert "Tagged 1" in hr.command_message

    def test_toggle_tag_via_input(self) -> None:
        st = _state(row=1)
        st.tag_input_action = "t"
        handle_tag_input_special(st, _act("enter", text="flex"))
        assert "flex" in st.buffer.tags_at(1)

    def test_remove_tag_via_input(self) -> None:
        st = _state("4 Goblin Guide  #core\n", row=0)
        st.tag_input_action = "r"
        handle_tag_input_special(st, _act("enter", text="core"))
        assert "core" not in st.buffer.tags_at(0)

    def test_filter_via_input(self) -> None:
        st = _state("4 Goblin Guide  #core\n4 Lava Spike\n", row=0)
        st.tag_input_action = "f"
        hr = handle_tag_input_special(st, _act("enter", text="core"))
        assert "Filter: 1/2 cards match" in hr.command_message
        assert st.tag_filter is not None

    def test_empty_enter_exits(self) -> None:
        st = _state(row=1)
        st.tag_input_action = "a"
        hr = handle_tag_input_special(st, _act("enter", text=""))
        assert hr.exit_to_normal is True
        assert st.insert_submode == InsertSubmode.CARD_SEARCH

    def test_char_key_is_noop(self) -> None:
        st = _state(row=1)
        assert handle_tag_input_special(st, _act("char", text="c")).command_message == ""


# ── handle_command ─────────────────────────────────────────────────


def _registry() -> CommandRegistry:
    reg = CommandRegistry()
    register_buffer_commands(reg)
    return reg


class TestHandleCommand:
    def test_empty_command_noop(self) -> None:
        st = _state()
        action = _act("enter", text="", action_type="command_submit")
        hr = handle_command(st, action, _registry(), None)
        assert hr == hr.__class__()

    def test_unknown_command_message(self) -> None:
        st = _state()
        hr = handle_command(
            st, _act("enter", text="boguscmd", action_type="command_submit"), _registry(), None
        )
        assert "Unknown command" in hr.command_message

    def test_search_mode_converts_to_find(self) -> None:
        st = _state()
        st.mode_mgr.transition(Mode.SEARCH)
        # :find with no card repo simply returns a message; just ensure no crash.
        hr = handle_command(
            st, _act("enter", text="bolt", action_type="command_submit"), _registry(), None
        )
        assert isinstance(hr.command_message, str)


# ── insert / command sub-mode handlers ─────────────────────────────


class TestInsertSpecial:
    def test_char_updates_query(self) -> None:
        st = _state()
        hr = handle_insert_special(st, _act("char", text="bol"))
        assert hr.search_query == "bol"

    def test_tab_requests_next(self) -> None:
        assert handle_insert_special(_state(), _act("tab")).search_query == "__next__"

    def test_shift_tab_requests_prev(self) -> None:
        assert handle_insert_special(_state(), _act("shift_tab")).search_query == "__prev__"

    def test_enter_confirms(self) -> None:
        assert handle_insert_special(_state(), _act("enter")).insert_confirm is True


class TestCommandSpecial:
    def test_no_completer_noop(self) -> None:
        st = _state()
        assert handle_command_special(st, _act("char", text="w")).command_ghost == ""

    def test_completion_ghost(self) -> None:
        st = _state()
        st.cmd_completer = CommandCompleter(_registry())
        hr = handle_command_special(st, _act("char", text="w"))
        # ghost is a string (possibly empty); should not raise.
        assert isinstance(hr.command_ghost, str)


# ── count_cards / resolve_cards ────────────────────────────────────


@pytest.fixture
def loaded_repo(db_factory: Callable[..., Database]) -> CardRepository:
    repo = CardRepository(db_factory())
    with open(FIXTURES_DIR / "scryfall_sample.json") as f:
        repo.bulk_insert([Card.from_scryfall(d) for d in json.load(f)])
    return repo


class TestCardHelpers:
    def test_count_cards(self) -> None:
        assert count_cards(Buffer.from_text("4 Goblin Guide\n2 Lava Spike\n")) == 6

    def test_count_cards_empty(self) -> None:
        assert count_cards(Buffer.from_text("// just a comment\n")) == 0

    def test_resolve_cards(self, loaded_repo: CardRepository) -> None:
        resolved = resolve_cards(
            Buffer.from_text("4 Lightning Bolt\n4 Goblin Guide\n"), loaded_repo
        )
        assert "Lightning Bolt" in resolved
        assert "Goblin Guide" in resolved

    def test_resolve_cards_degrades_on_corrupt_json_cell(
        self, loaded_repo: CardRepository
    ) -> None:
        """A corrupt JSON cell (e.g. interrupted sync) must degrade to
        unresolved cards, not crash every render (regression: only
        sqlite3.Error was caught, json.JSONDecodeError escaped)."""
        conn = loaded_repo._db.connect()
        conn.execute(
            "UPDATE cards SET legalities = '{broken' WHERE name = ?",
            ("Lightning Bolt",),
        )
        conn.commit()
        resolved = resolve_cards(
            Buffer.from_text("4 Lightning Bolt\n"), loaded_repo
        )
        assert resolved == {}


class TestMarkAdjustment:
    """Marks must track their lines across inserts and deletes."""

    def test_marks_shift_up_after_dd_above(self) -> None:
        st = _state(row=1)  # deck has cards on rows 1-3
        st.marks = st.marks.set("a", 3)
        handle_operator(st, ParsedAction("operator", "dd"))
        mark = st.marks.get("a")
        assert mark is not None
        assert mark.row == 2

    def test_mark_on_deleted_line_is_cleared(self) -> None:
        st = _state(row=2)
        st.marks = st.marks.set("a", 2)
        handle_operator(st, ParsedAction("operator", "dd"))
        assert st.marks.get("a") is None

    def test_marks_shift_down_after_put(self) -> None:
        st = _state(row=1)
        st.marks = st.marks.set("a", 3)
        # Yank current line then put below cursor
        handle_operator(st, ParsedAction("operator", "yy"))
        handle_normal_special(st, ParsedAction("special", "p"))
        mark = st.marks.get("a")
        assert mark is not None
        assert mark.row == 4

    def test_marks_shift_down_after_counted_put(self) -> None:
        """3p must shift marks by the FIRST inserted row, not the row of
        the last paste (regression: marks below the cursor drifted into
        the pasted block)."""
        st = _state(row=1)
        st.marks = st.marks.set("a", 3)
        handle_operator(st, ParsedAction("operator", "yy"))
        handle_normal_special(st, ParsedAction("special", "p", count=3))
        mark = st.marks.get("a")
        assert mark is not None
        assert mark.row == 6  # original row 3 pushed down by 3 pasted lines

    def test_marks_shift_after_x_delete(self) -> None:
        st = _state(row=1)
        st.marks = st.marks.set("b", 3)
        handle_normal_special(st, ParsedAction("special", "x"))
        mark = st.marks.get("b")
        assert mark is not None
        assert mark.row == 2

    def test_marks_unchanged_by_yank(self) -> None:
        st = _state(row=1)
        st.marks = st.marks.set("a", 3)
        handle_operator(st, ParsedAction("operator", "yy"))
        mark = st.marks.get("a")
        assert mark is not None
        assert mark.row == 3


# ── Zone moves (ms/mm/md) ──────────────────────────────────────────


class TestZoneMoves:
    def test_ms_moves_all_copies_to_sideboard(self) -> None:
        state = _state(row=1)  # "4 Goblin Guide"
        result = handle_normal_special(state, _act("ms", count=0))
        lines = [bl.text for bl in state.buffer.get_lines()]
        assert "SB: 4 Goblin Guide" in lines
        assert "4 Goblin Guide" not in lines
        assert state.modified
        assert "Moved 4x Goblin Guide to sideboard" in result.command_message
        # Cursor follows the card
        assert state.cursor.row == lines.index("SB: 4 Goblin Guide")

    def test_counted_ms_splits_entry(self) -> None:
        state = _state(row=1)
        handle_normal_special(state, _act("ms", count=1))
        lines = [bl.text for bl in state.buffer.get_lines()]
        assert "3 Goblin Guide" in lines
        assert "SB: 1 Goblin Guide" in lines

    def test_md_moves_sideboard_card_back(self) -> None:
        state = _state("4 Goblin Guide\n\nSB: 2 Eidolon of the Great Revel\n", row=2)
        handle_normal_special(state, _act("md", count=0))
        lines = [bl.text for bl in state.buffer.get_lines()]
        assert "2 Eidolon of the Great Revel" in lines
        assert "SB: 2 Eidolon of the Great Revel" not in lines

    def test_mm_moves_to_maybeboard(self) -> None:
        state = _state(row=1)
        handle_normal_special(state, _act("mm", count=0))
        lines = [bl.text for bl in state.buffer.get_lines()]
        assert "MB: 4 Goblin Guide" in lines

    def test_ms_does_not_set_mark(self) -> None:
        state = _state(row=1)
        handle_normal_special(state, _act("ms", count=0))
        assert state.marks.get("s") is None

    def test_other_letters_still_set_marks(self) -> None:
        state = _state(row=1)
        result = handle_normal_special(state, _act("ma"))
        assert "Mark 'a' set" in result.command_message
        assert state.marks.get("a") is not None

    def test_zone_move_records_history_for_undo(self) -> None:
        state = _state(row=1)
        original = state.buffer.to_text()
        handle_normal_special(state, _act("ms", count=0))
        restored = state.history.undo()
        assert restored is not None
        assert restored.to_text() == original

    def test_dot_repeats_zone_move(self) -> None:
        state = _state(row=1)
        handle_normal_special(state, _act("ms", count=0))
        # Move cursor to the next main-deck card and repeat
        state.cursor = Cursor(row=state.buffer.get_lines().index(
            next(bl for bl in state.buffer.get_lines()
                 if bl.text == "4 Monastery Swiftspear")
        ))
        handle_normal_special(state, _act("."))
        lines = [bl.text for bl in state.buffer.get_lines()]
        assert "SB: 4 Monastery Swiftspear" in lines

    def test_noop_on_comment_line_reports_error(self) -> None:
        state = _state(row=0)  # "// Creatures"
        result = handle_normal_special(state, _act("ms", count=0))
        assert result.error
        assert not state.modified

"""Tests for newly wired features: dot repeat, marks, visual ops, / search."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult, ParsedAction
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.services.history_service import HistoryService
from vimtg.tui.screens.key_handler import (
    EditorState,
    handle_mode_switch,
    handle_normal_special,
    handle_operator,
)


def _make_state(text: str = "4 Lightning Bolt\n2 Counterspell\n1 Abrade\n") -> EditorState:
    buf = Buffer.from_text(text)
    history = HistoryService()
    history.initialize(buf)
    return EditorState(
        buffer=buf,
        cursor=Cursor(row=0),
        mode_mgr=ModeManager(),
        registers=RegisterStore(),
        history=history,
        modified=False,
        resolved_cards={},
    )


class TestDotRepeat:
    def test_dot_records_operator(self) -> None:
        state = _make_state()
        action = ParsedAction("operator", "dd", count=1)
        handle_operator(state, action)
        assert state.dot_repeat.last_action is not None
        assert state.dot_repeat.last_action.operator == "dd"

    def test_dot_records_quantity(self) -> None:
        state = _make_state()
        action = ParsedAction("special", "+")
        handle_normal_special(state, action)
        assert state.dot_repeat.last_action is not None
        assert state.dot_repeat.last_action.operator == "+"

    def test_dot_replays_quantity(self) -> None:
        state = _make_state()
        handle_normal_special(state, ParsedAction("special", "+"))
        qty_before = state.buffer.quantity_at(0)
        handle_normal_special(state, ParsedAction("special", "."))
        qty_after = state.buffer.quantity_at(0)
        assert qty_after == qty_before + 1

    def test_dot_replays_delete(self) -> None:
        state = _make_state()
        # Delete first card
        handle_normal_special(state, ParsedAction("special", "x"))
        count_after_first = state.buffer.line_count()
        # Dot repeat should delete another card
        handle_normal_special(state, ParsedAction("special", "."))
        assert state.buffer.line_count() < count_after_first


class TestMarks:
    def test_set_and_jump_to_mark(self) -> None:
        state = _make_state()
        state.cursor = state.cursor.move_to(2, 0)
        handle_normal_special(state, ParsedAction("special", "ma"))
        state.cursor = state.cursor.move_to(0, 0)
        handle_normal_special(state, ParsedAction("special", "'a"))
        assert state.cursor.row == 2

    def test_jump_to_unset_mark(self) -> None:
        state = _make_state()
        result = handle_normal_special(
            state, ParsedAction("special", "'z"),
        )
        assert "not set" in result.command_message

    def test_mark_set_message(self) -> None:
        state = _make_state()
        result = handle_normal_special(
            state, ParsedAction("special", "mb"),
        )
        assert "Mark 'b'" in result.command_message


class TestVisualSelection:
    def test_visual_sets_anchor(self) -> None:
        state = _make_state()
        state.cursor = state.cursor.move_to(1, 0)
        handle_mode_switch(state, ParsedAction("mode_switch", "V"))
        assert state.visual_anchor == 1

    def test_escape_clears_anchor(self) -> None:
        state = _make_state()
        state.visual_anchor = 1
        handle_mode_switch(state, ParsedAction("mode_switch", "escape"))
        assert state.visual_anchor is None

    def test_visual_delete_uses_range(self) -> None:
        state = _make_state()
        # Enter visual at row 0, move cursor to row 1
        state.visual_anchor = 0
        state.cursor = state.cursor.move_to(1, 0)
        state.mode_mgr.transition(Mode.VISUAL_LINE)

        handle_operator(state, ParsedAction("operator", "d"))
        # Should have deleted 2 lines (rows 0-1)
        assert state.buffer.line_count() == 1
        assert "Abrade" in state.buffer.get_line(0).text
        assert state.visual_anchor is None


class TestSearchMode:
    def test_slash_enters_search(self) -> None:
        state = _make_state()
        result = handle_mode_switch(
            state, ParsedAction("mode_switch", "/"),
        )
        assert result.enter_search is True

    def test_keymap_slash_to_search_mode(self) -> None:
        km = KeyMap()
        result, action = km.feed("/")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "/"

    def test_keymap_mark_multi_key(self) -> None:
        km = KeyMap()
        result, _ = km.feed("m")
        assert result == KeyResult.PENDING
        result, action = km.feed("a")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "ma"

    def test_keymap_quote_mark_jump(self) -> None:
        km = KeyMap()
        result, _ = km.feed("'")
        assert result == KeyResult.PENDING
        result, action = km.feed("b")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "'b"


class TestMacroRecording:
    def test_q_register_starts_and_q_stop_ends(self) -> None:
        state = _make_state()
        hr = handle_normal_special(state, ParsedAction("special", "qa"))
        assert state.macros.is_recording
        assert state.macros.recording_register == "a"
        assert "recording @a" in hr.command_message
        state.macros.record_key("j")
        hr = handle_normal_special(state, ParsedAction("special", "q_stop"))
        assert not state.macros.is_recording
        assert "Recorded @a (1 keys)" in hr.command_message

    def test_play_returns_recorded_keys(self) -> None:
        state = _make_state()
        handle_normal_special(state, ParsedAction("special", "qb"))
        state.macros.record_key("j")
        state.macros.record_key("x")
        handle_normal_special(state, ParsedAction("special", "q_stop"))
        hr = handle_normal_special(state, ParsedAction("special", "@b"))
        assert hr.replay_keys == ("j", "x")

    def test_play_empty_register_reports(self) -> None:
        state = _make_state()
        hr = handle_normal_special(state, ParsedAction("special", "@z"))
        assert "Nothing recorded" in hr.command_message
        assert hr.replay_keys == ()


class TestTagFilterWiring:
    """:filter and tf must actually drive the deck view's filter state."""

    def test_cmd_filter_sets_context_filter(self) -> None:
        from vimtg.editor.command_handlers.tag_cmds import cmd_filter
        from vimtg.editor.commands import EditorContext, ParsedCommand
        from vimtg.editor.buffer import Buffer
        from vimtg.editor.cursor import Cursor

        buf = Buffer.from_text("4 Lightning Bolt  #burn\n4 Goblin Guide\n")
        ctx = EditorContext()
        cmd_filter(buf, Cursor(), ParsedCommand(name="filter", args="burn"), ctx)
        assert ctx.tag_filter_set
        assert ctx.tag_filter is not None
        assert "1/2" in ctx.message

    def test_cmd_filter_bang_clears(self) -> None:
        from vimtg.editor.command_handlers.tag_cmds import cmd_filter
        from vimtg.editor.commands import EditorContext, ParsedCommand
        from vimtg.editor.buffer import Buffer
        from vimtg.editor.cursor import Cursor

        buf = Buffer.from_text("4 Lightning Bolt\n")
        ctx = EditorContext()
        cmd_filter(buf, Cursor(), ParsedCommand(name="filter", bang=True), ctx)
        assert ctx.tag_filter_set
        assert ctx.tag_filter is None

    def test_filter_dims_nonmatching_lines_in_renderer(self) -> None:
        from vimtg.editor.buffer import Buffer
        from vimtg.tui.deck_renderer import render_line

        buf = Buffer.from_text("4 Lightning Bolt\n")
        normal = render_line(0, buf, 99, {})
        dimmed = render_line(0, buf, 99, {}, dimmed=True)
        assert normal[0].markup != dimmed[0].markup

"""Tests for the per-card comment flow (A key -> COMMENT_INPUT submode)."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.modes import ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import (
    EditorState,
    InsertSubmode,
    handle_comment_input_special,
    handle_normal_special,
)
from vimtg.services.history_service import HistoryService


def _make_state(text: str, cursor_row: int = 0) -> EditorState:
    buf = Buffer.from_text(text)
    history = HistoryService()
    history.initialize(buf)
    return EditorState(
        buffer=buf,
        cursor=Cursor(row=cursor_row),
        mode_mgr=ModeManager(),
        registers=RegisterStore(),
        history=history,
        modified=False,
        resolved_cards={},
    )


class TestEnterCommentInput:
    def test_a_on_card_line_enters_comment_input(self) -> None:
        state = _make_state("4 Lightning Bolt\n")
        hr = handle_normal_special(state, ParsedAction("special", "A"))
        assert hr.enter_comment_input is True
        assert state.insert_submode == InsertSubmode.COMMENT_INPUT

    def test_a_prefills_existing_comment(self) -> None:
        state = _make_state("4 Bolt  // wincon\n")
        hr = handle_normal_special(state, ParsedAction("special", "A"))
        assert hr.comment_prefill == "wincon"

    def test_a_on_non_card_line_rejected(self) -> None:
        state = _make_state("// Mainboard\n4 Bolt\n")
        hr = handle_normal_special(state, ParsedAction("special", "A"))
        assert hr.enter_comment_input is False
        assert state.insert_submode != InsertSubmode.COMMENT_INPUT
        assert hr.command_message == "Comments attach to card lines"


class TestCommentInputSpecial:
    def _in_comment_mode(self, text: str, row: int = 0) -> EditorState:
        state = _make_state(text, cursor_row=row)
        handle_normal_special(state, ParsedAction("special", "A"))
        return state

    def test_enter_sets_comment(self) -> None:
        state = self._in_comment_mode("4 Bolt\n")
        hr = handle_comment_input_special(
            state, ParsedAction("special", "enter", text="wincon")
        )
        assert hr.exit_to_normal is True
        assert state.buffer.get_line(0).text == "4 Bolt  // wincon"
        assert state.modified is True

    def test_enter_empty_removes_comment(self) -> None:
        state = self._in_comment_mode("4 Bolt  // old\n")
        hr = handle_comment_input_special(
            state, ParsedAction("special", "enter", text="")
        )
        assert state.buffer.get_line(0).text == "4 Bolt"
        assert hr.command_message == "Comment removed"

    def test_enter_unchanged_records_no_history(self) -> None:
        state = self._in_comment_mode("4 Bolt  // same\n")
        assert state.history.can_undo is False
        handle_comment_input_special(
            state, ParsedAction("special", "enter", text="same")
        )
        assert state.history.can_undo is False
        assert state.modified is False

    def test_typing_does_not_touch_buffer(self) -> None:
        state = self._in_comment_mode("4 Bolt\n")
        handle_comment_input_special(
            state, ParsedAction("special", "char", text="win")
        )
        assert state.buffer.get_line(0).text == "4 Bolt"

    def test_enter_resets_submode(self) -> None:
        state = self._in_comment_mode("4 Bolt\n")
        handle_comment_input_special(
            state, ParsedAction("special", "enter", text="x")
        )
        assert state.insert_submode == InsertSubmode.CARD_SEARCH

    def test_comment_preserves_tags(self) -> None:
        state = self._in_comment_mode("4 Bolt  #burn\n")
        handle_comment_input_special(
            state, ParsedAction("special", "enter", text="wincon")
        )
        assert state.buffer.get_line(0).text == "4 Bolt  #burn  // wincon"

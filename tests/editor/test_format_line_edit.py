"""Format-field autocomplete and unknown-format notification."""

from __future__ import annotations

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.lint import lint_buffer
from vimtg.editor.modes import ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import (
    EditorState,
    InsertSubmode,
    handle_line_edit_special,
    handle_mode_switch,
)
from vimtg.services.history_service import HistoryService


def _state(text: str = "// Format:\n4 Lightning Bolt\n") -> EditorState:
    buffer = Buffer.from_text(text)
    state = EditorState(
        buffer=buffer,
        cursor=Cursor(),
        mode_mgr=ModeManager(),
        registers=RegisterStore(),
        history=HistoryService(),
        modified=False,
        resolved_cards={},
        settings=Settings(),
    )
    state.history.initialize(buffer)
    return state


def _enter_format_edit(state: EditorState) -> None:
    hr = handle_mode_switch(state, ParsedAction("mode_switch", "i"))
    assert hr.enter_line_edit
    assert state.insert_submode is InsertSubmode.LINE_EDIT
    assert state.line_edit_prefix.startswith("// Format:")


def _char(state: EditorState, text: str):
    return handle_line_edit_special(
        state, ParsedAction("special", "char", text=text, cursor_pos=len(text))
    )


class TestFormatGhost:
    def test_typing_ghosts_known_format(self):
        state = _state()
        _enter_format_edit(state)
        hr = _char(state, "mod")
        assert hr.command_ghost == "modern"

    def test_case_insensitive(self):
        state = _state()
        _enter_format_edit(state)
        hr = _char(state, "Com")
        assert hr.command_ghost == "commander"

    def test_no_match_no_ghost(self):
        state = _state()
        _enter_format_edit(state)
        hr = _char(state, "xyz")
        assert hr.command_ghost == ""

    def test_empty_value_no_ghost(self):
        state = _state()
        _enter_format_edit(state)
        hr = _char(state, "")
        assert hr.command_ghost == ""

    def test_non_format_line_has_no_ghost(self):
        state = _state("// Author:\n4 Lightning Bolt\n")
        hr = handle_mode_switch(state, ParsedAction("mode_switch", "i"))
        assert hr.enter_line_edit
        hr = _char(state, "mod")
        assert hr.command_ghost == ""


class TestTabAccept:
    def test_tab_completes_value_and_buffer_line(self):
        state = _state()
        _enter_format_edit(state)
        _char(state, "comm")
        hr = handle_line_edit_special(
            state, ParsedAction("special", "tab", text="comm", cursor_pos=4)
        )
        assert hr.command_accept == "commander"
        assert state.buffer.get_line(0).text == "// Format: commander"

    def test_tab_without_match_is_noop(self):
        state = _state()
        _enter_format_edit(state)
        _char(state, "xyz")
        hr = handle_line_edit_special(
            state, ParsedAction("special", "tab", text="xyz", cursor_pos=3)
        )
        assert hr.command_accept == ""
        assert state.buffer.get_line(0).text == "// Format: xyz"


class TestUnknownFormatNotice:
    def _confirm(self, state: EditorState, text: str):
        _char(state, text)
        return handle_line_edit_special(
            state, ParsedAction("special", "enter", text=text)
        )

    def test_unknown_format_warns_on_confirm(self):
        state = _state()
        _enter_format_edit(state)
        hr = self._confirm(state, "edh")
        assert "Unknown format 'edh'" in hr.command_message
        assert "no legality checking" in hr.command_message

    def test_known_format_confirms_silently(self):
        state = _state()
        _enter_format_edit(state)
        hr = self._confirm(state, "commander")
        assert hr.command_message == ""

    def test_capitalized_known_format_confirms_silently(self):
        state = _state()
        _enter_format_edit(state)
        hr = self._confirm(state, "Commander")
        assert hr.command_message == ""

    def test_empty_value_confirms_silently(self):
        state = _state()
        _enter_format_edit(state)
        hr = self._confirm(state, "")
        assert hr.command_message == ""


class TestLintAnchor:
    def test_unknown_format_warning_anchors_to_format_line(self):
        buf = Buffer.from_text("// Format: edh\n60 Forest\n")
        result = lint_buffer(buf, {})
        err = result.line_errors.get(0)
        assert err is not None
        assert err.level == "warning"
        assert "Unknown format" in err.message
        assert not any(
            "Unknown format" in e.message for e in result.deck_errors
        )

    def test_known_format_has_no_format_line_warning(self):
        buf = Buffer.from_text("// Format: modern\n60 Forest\n")
        result = lint_buffer(buf, {})
        err = result.line_errors.get(0)
        assert err is None or "Unknown format" not in err.message

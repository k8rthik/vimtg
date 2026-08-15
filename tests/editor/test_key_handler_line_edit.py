"""Tests for line-edit mode in key_handler — plain-text editing of non-card lines."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.modes import ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import (
    EditorState,
    InsertSubmode,
    handle_line_edit_special,
    handle_mode_switch,
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


class TestIModeSwitch:
    def test_i_enters_line_edit(self) -> None:
        state = _make_state("// Creature\n4 Goblin Guide\n")
        action = ParsedAction("mode_switch", "i")
        hr = handle_mode_switch(state, action)
        assert hr.enter_line_edit is True
        assert state.insert_submode == InsertSubmode.LINE_EDIT
        assert state.line_edit_original == "// Creature"
        assert state.line_edit_row == 0

    def test_i_on_comment_sets_prefix(self) -> None:
        state = _make_state("// Creature\n4 Goblin Guide\n")
        action = ParsedAction("mode_switch", "i")
        handle_mode_switch(state, action)
        assert state.line_edit_prefix == "// "

    def test_i_on_comment_no_trailing_space(self) -> None:
        state = _make_state("//Creature\n4 Goblin Guide\n")
        action = ParsedAction("mode_switch", "i")
        handle_mode_switch(state, action)
        assert state.line_edit_prefix == "//"

    def test_i_on_card_line_no_prefix(self) -> None:
        state = _make_state("// Creature\n4 Goblin Guide\n", cursor_row=1)
        action = ParsedAction("mode_switch", "i")
        handle_mode_switch(state, action)
        assert state.line_edit_prefix == ""
        assert state.line_edit_original == "4 Goblin Guide"

    def test_i_on_blank_line_no_prefix(self) -> None:
        state = _make_state("// Creature\n\n4 Goblin Guide\n", cursor_row=1)
        action = ParsedAction("mode_switch", "i")
        handle_mode_switch(state, action)
        assert state.line_edit_prefix == ""
        assert state.line_edit_original == ""

    def test_i_on_metadata_sets_prefix(self) -> None:
        state = _make_state("// Deck: Burn\n// Creature\n4 Goblin Guide\n")
        action = ParsedAction("mode_switch", "i")
        handle_mode_switch(state, action)
        assert state.line_edit_prefix == "// "
        assert state.line_edit_original == "// Deck: Burn"


class TestLineEditSpecial:
    def test_char_updates_buffer_with_prefix(self) -> None:
        state = _make_state("// Creature\n4 Goblin Guide\n")
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_row = 0
        state.line_edit_original = "// Creature"
        state.line_edit_prefix = "// "

        # User typed "Creatures" (keymap accumulates only editable part)
        action = ParsedAction("special", "char", text="Creatures")
        handle_line_edit_special(state, action)
        assert state.buffer.get_line(0).text == "// Creatures"

    def test_backspace_updates_buffer_with_prefix(self) -> None:
        state = _make_state("// Creature\n4 Goblin Guide\n")
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_row = 0
        state.line_edit_original = "// Creature"
        state.line_edit_prefix = "// "

        action = ParsedAction("special", "backspace", text="Creatur")
        handle_line_edit_special(state, action)
        assert state.buffer.get_line(0).text == "// Creatur"

    def test_char_on_non_comment_line_no_prefix(self) -> None:
        state = _make_state("4 Goblin Guide\n")
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_row = 0
        state.line_edit_original = "4 Goblin Guide"
        state.line_edit_prefix = ""

        action = ParsedAction("special", "char", text="4 Lightning Bolt")
        handle_line_edit_special(state, action)
        assert state.buffer.get_line(0).text == "4 Lightning Bolt"

    def test_enter_confirms_and_exits(self) -> None:
        state = _make_state("// Creature\n4 Goblin Guide\n")
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_row = 0
        state.line_edit_original = "// Creature"
        state.line_edit_prefix = "// "
        state.buffer = state.buffer.set_line(0, "// Spells")

        action = ParsedAction("special", "enter", text="Spells")
        hr = handle_line_edit_special(state, action)
        assert hr.exit_to_normal is True
        assert state.modified is True
        assert state.line_edit_original is None
        assert state.line_edit_row is None

    def test_enter_records_history(self) -> None:
        state = _make_state("// Creature\n4 Goblin Guide\n")
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_row = 0
        state.line_edit_original = "// Creature"
        state.line_edit_prefix = "// "
        state.buffer = state.buffer.set_line(0, "// Spells")

        action = ParsedAction("special", "enter", text="Spells")
        handle_line_edit_special(state, action)
        restored = state.history.undo()
        assert restored is not None

    def test_escape_leaves_original_for_restore(self) -> None:
        """Escape from line edit — line_edit_original stays set so MainScreen can restore."""
        state = _make_state("// Creature\n4 Goblin Guide\n")
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_row = 0
        state.line_edit_original = "// Creature"
        state.line_edit_prefix = "// "
        state.buffer = state.buffer.set_line(0, "// Foo")

        escape_action = ParsedAction("mode_switch", "escape")
        hr = handle_mode_switch(state, escape_action)
        assert hr.exit_to_normal is True
        assert state.line_edit_original == "// Creature"

    def test_empty_editable_text_preserves_prefix(self) -> None:
        """Backspacing all editable text still keeps the // prefix in buffer."""
        state = _make_state("// Creature\n4 Goblin Guide\n")
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_row = 0
        state.line_edit_original = "// Creature"
        state.line_edit_prefix = "// "

        action = ParsedAction("special", "backspace", text="")
        handle_line_edit_special(state, action)
        assert state.buffer.get_line(0).text == "// "

    def test_row_out_of_bounds_safe(self) -> None:
        """If line_edit_row is somehow out of bounds, don't crash."""
        state = _make_state("// Creature\n")
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_row = 99
        state.line_edit_original = "// Creature"
        state.line_edit_prefix = "// "

        action = ParsedAction("special", "char", text="x")
        hr = handle_line_edit_special(state, action)
        assert hr.exit_to_normal is False

    def test_delete_key_updates_buffer(self) -> None:
        state = _make_state("// Creature\n4 Goblin Guide\n")
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_row = 0
        state.line_edit_original = "// Creature"
        state.line_edit_prefix = "// "

        action = ParsedAction("special", "delete", text="reature")
        handle_line_edit_special(state, action)
        assert state.buffer.get_line(0).text == "// reature"

    def test_cursor_move_is_noop(self) -> None:
        state = _make_state("// Creature\n4 Goblin Guide\n")
        state.insert_submode = InsertSubmode.LINE_EDIT
        state.line_edit_row = 0
        state.line_edit_original = "// Creature"
        state.line_edit_prefix = "// "

        action = ParsedAction("special", "cursor_move", text="Creature", cursor_pos=4)
        hr = handle_line_edit_special(state, action)
        assert hr.exit_to_normal is False
        # Buffer should NOT be updated on cursor_move
        assert state.buffer.get_line(0).text == "// Creature"

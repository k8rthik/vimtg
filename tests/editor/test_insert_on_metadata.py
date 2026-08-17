"""o/O on a metadata line must not split the metadata block."""

from __future__ import annotations

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer, LineType
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.modes import ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import EditorState, handle_mode_switch
from vimtg.services.history_service import HistoryService

_TEXT = "// Deck: Burn\n// Format: modern\n\n4 Lightning Bolt\n"


def _state(row: int) -> EditorState:
    buffer = Buffer.from_text(_TEXT)
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


def _press(state: EditorState, key: str) -> None:
    hr = handle_mode_switch(state, ParsedAction("mode_switch", key))
    assert hr.enter_insert


def _metadata_block_is_intact(buf: Buffer) -> bool:
    return (
        buf.get_line(0).line_type is LineType.METADATA
        and buf.get_line(1).line_type is LineType.METADATA
    )


class TestInsertOnMetadata:
    def test_o_on_first_metadata_line_opens_below_block(self):
        state = _state(row=0)
        _press(state, "o")
        assert _metadata_block_is_intact(state.buffer)
        assert state.cursor.row == 2
        assert state.buffer.get_line(2).line_type is LineType.BLANK

    def test_o_on_last_metadata_line_opens_below_block(self):
        state = _state(row=1)
        _press(state, "o")
        assert _metadata_block_is_intact(state.buffer)
        assert state.cursor.row == 2

    def test_shift_o_on_metadata_also_opens_below_block(self):
        # O (above) between '// Deck:' and '// Format:' was the bug
        state = _state(row=1)
        _press(state, "O")
        assert _metadata_block_is_intact(state.buffer)
        assert state.cursor.row == 2

    def test_o_on_card_line_unchanged(self):
        state = _state(row=3)
        _press(state, "o")
        assert state.cursor.row == 4
        assert state.buffer.get_line(4).line_type is LineType.BLANK

    def test_shift_o_on_card_line_unchanged(self):
        state = _state(row=3)
        _press(state, "O")
        assert state.buffer.get_line(3).line_type is LineType.BLANK
        assert state.buffer.get_line(4).line_type is LineType.CARD_ENTRY

    def test_metadata_only_buffer_appends_at_end(self):
        buffer = Buffer.from_text("// Deck: X\n// Format: modern\n")
        state = _state(row=0)
        state.buffer = buffer
        _press(state, "o")
        assert _metadata_block_is_intact(state.buffer)
        assert state.cursor.row == 2

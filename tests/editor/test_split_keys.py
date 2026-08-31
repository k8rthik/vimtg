"""Tests for the S split-key sequences (keymap + normal-mode handler)."""

from __future__ import annotations

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult
from vimtg.editor.modes import ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import EditorState, handle_normal_special
from vimtg.services.history_service import HistoryService


def _state() -> EditorState:
    buffer = Buffer.from_text("4 Lightning Bolt\n")
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


class TestKeymapSplitSequences:
    def test_s_pends(self):
        km = KeyMap()
        result, action = km.feed("S")
        assert result == KeyResult.PENDING
        assert action is None

    def test_split_sub_keys_complete_as_specials(self):
        for sub in ("v", "h", "s", "c", "r", "a"):
            km = KeyMap()
            km.feed("S")
            result, action = km.feed(sub)
            assert result == KeyResult.COMPLETE
            assert action is not None
            assert action.action_type == "special"
            assert action.action == f"S{sub}"

    def test_unknown_sub_key_no_match(self):
        km = KeyMap()
        km.feed("S")
        result, action = km.feed("z")
        assert result == KeyResult.NO_MATCH
        assert action is None


class TestSplitKeyHandlers:
    def _handle(self, key: str):
        km = KeyMap()
        km.feed("S")
        _, action = km.feed(key[1])
        assert action is not None
        return handle_normal_special(_state(), action)

    def test_sv_prefills_vsplit_command(self):
        hr = self._handle("Sv")
        assert hr.enter_command
        assert hr.command_prefill == "vsplit "

    def test_sh_prefills_split_command(self):
        hr = self._handle("Sh")
        assert hr.enter_command
        assert hr.command_prefill == "split "

    def test_ss_requests_pane_focus_switch(self):
        hr = self._handle("Ss")
        assert hr.focus_next_pane

    def test_sc_requests_split_close(self):
        hr = self._handle("Sc")
        assert hr.split_close

    def test_sr_runs_edhrec_command(self):
        hr = self._handle("Sr")
        assert hr.run_ex_command == "edhrec"

    def test_sa_runs_analytics_command(self):
        hr = self._handle("Sa")
        assert hr.run_ex_command == "analytics"

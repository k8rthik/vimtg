"""Window keys (vim's Ctrl-W prefix) and the Space leader: the keymap
sequences and what the normal-mode handler asks the screen to do."""

from __future__ import annotations

import pytest

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import EditorState, HandlerResult, handle_normal_special
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


def _press(*keys: str) -> HandlerResult:
    km = KeyMap()
    result, action = KeyResult.NO_MATCH, None
    for key in keys:
        result, action = km.feed(key)
    assert result == KeyResult.COMPLETE and action is not None, keys
    assert action.action_type == "special"
    return handle_normal_special(_state(), action)


class TestWindowPrefix:
    def test_ctrl_w_pends_and_shows_as_caret_w(self) -> None:
        km = KeyMap()
        assert km.feed("ctrl_w")[0] == KeyResult.PENDING
        assert km.pending_display == "^W"

    def test_unknown_window_key_is_dropped(self) -> None:
        km = KeyMap()
        km.feed("ctrl_w")
        assert km.feed("z") == (KeyResult.NO_MATCH, None)

    def test_w_focuses_the_other_window(self) -> None:
        assert _press("ctrl_w", "w") == HandlerResult(focus_other_window=True)

    @pytest.mark.parametrize("key", ["v", "s", "W", "h", "j", "k", "l", "c", "q", "o"])
    def test_second_deck_window_keys_are_gone(self, key: str) -> None:
        km = KeyMap()
        km.feed("ctrl_w")
        assert km.feed(key) == (KeyResult.NO_MATCH, None)

    def test_s_is_no_longer_a_window_prefix(self) -> None:
        assert KeyMap().feed("S")[0] != KeyResult.PENDING

    def test_visual_mode_ignores_the_window_and_leader_prefixes(self) -> None:
        for key in ("ctrl_w", " "):
            km = KeyMap(mode=Mode.VISUAL)
            assert km.feed(key) == (KeyResult.NO_MATCH, None)


class TestSpaceLeader:
    def test_space_pends(self) -> None:
        km = KeyMap()
        assert km.feed(" ")[0] == KeyResult.PENDING
        assert km.pending_menu == "space"

    def test_a_and_r_toggle_their_panes(self) -> None:
        assert _press(" ", "a").toggle_pane == "analytics"
        assert _press(" ", "r").toggle_pane == "edhrec"

    def test_h_opens_the_sample_hand(self) -> None:
        assert _press(" ", "h").run_ex_command == "hand"

    def test_unknown_leader_key_is_dropped(self) -> None:
        km = KeyMap()
        km.feed(" ")
        assert km.feed("x") == (KeyResult.NO_MATCH, None)

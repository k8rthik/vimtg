"""gh opens the history overlay: keymap parses it, the session requests it."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult, ParsedAction
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import EditorState, handle_normal_special
from vimtg.services.history_service import HistoryService

DECK = "// Creatures\n4 Goblin Guide\n"


def _state() -> EditorState:
    buf = Buffer.from_text(DECK)
    history = HistoryService()
    history.initialize(buf)
    return EditorState(
        buffer=buf,
        cursor=Cursor(row=1),
        mode_mgr=ModeManager(),
        registers=RegisterStore(),
        history=history,
        modified=False,
        resolved_cards={},
    )


class TestKeymapGh:
    def test_gh_completes_as_special(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        r1, a1 = km.feed("g")
        assert r1 == KeyResult.PENDING and a1 is None
        result, action = km.feed("h")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "special"
        assert action.action == "gh"

    def test_gh_does_not_break_gg(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("g")
        result, action = km.feed("g")
        assert result == KeyResult.COMPLETE
        assert action is not None and action.action == "gg"


class TestSessionGh:
    def test_gh_requests_history_screen(self) -> None:
        st = _state()
        hr = handle_normal_special(st, ParsedAction("special", "gh"))
        assert hr.open_history_screen is True
        assert st.buffer.to_text() == DECK

"""n / N repeat the last / or ?; H / M / L use the deck view's band."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.search_cmds import find_card_row
from vimtg.editor.commands import CommandRegistry
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.modes import Mode, ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import (
    EditorState,
    handle_command,
    handle_motion,
    handle_normal_special,
)
from vimtg.services.history_service import HistoryService

DECK = (
    "// Creatures\n"  # 0
    "4 Goblin Guide\n"  # 1
    "4 Monastery Swiftspear\n"  # 2
    "\n"  # 3
    "// Instants\n"  # 4
    "4 Lightning Bolt\n"  # 5
    "4 Lightning Helix\n"  # 6
    "2 Boros Charm\n"  # 7
)


def _state(row: int = 0) -> EditorState:
    buf = Buffer.from_text(DECK)
    history = HistoryService()
    history.initialize(buf)
    return EditorState(
        buffer=buf, cursor=Cursor(row=row), mode_mgr=ModeManager(),
        registers=RegisterStore(), history=history, modified=False,
        resolved_cards={},
    )


def _search(st: EditorState, text: str, *, backward: bool = False) -> None:
    """/text (or ?text) then Enter."""
    if st.mode_mgr.current != Mode.SEARCH:
        st.mode_mgr.transition(Mode.SEARCH)
    st.search_backward = backward
    handle_command(
        st, ParsedAction("command_submit", "enter", text=text), CommandRegistry(), None,
    )


def _key(key: str, count: int = 1) -> ParsedAction:
    return ParsedAction("special", key, count)


class TestFindCardRow:
    def test_forward_wraps(self) -> None:
        buf = Buffer.from_text(DECK)
        assert find_card_row(buf, 6, "goblin") == 1

    def test_backward_wraps(self) -> None:
        buf = Buffer.from_text(DECK)
        assert find_card_row(buf, 1, "lightning", backward=True) == 6

    def test_skips_non_card_lines_and_wraps_back_to_the_start(self) -> None:
        buf = Buffer.from_text(DECK)
        # "Instants" header matches "i" but is not a card line
        assert find_card_row(buf, 2, "instant") is None
        # The only match is the start row: vim wraps round to it
        assert find_card_row(buf, 7, "boros") == 7


class TestRepeatFind:
    def test_slash_search_records_pattern(self) -> None:
        st = _state()
        _search(st, "bolt")
        assert st.cursor.row == 5
        assert st.last_find == "bolt"

    def test_question_mark_searches_backward(self) -> None:
        st = _state(row=6)
        _search(st, "lightning", backward=True)
        assert st.cursor.row == 5
        assert st.last_find == "lightning"

    def test_invalid_pattern_not_recorded(self) -> None:
        st = _state()
        _search(st, "bolt")
        _search(st, "[")
        assert st.last_find == "bolt"

    def test_n_moves_forward(self) -> None:
        st = _state()
        _search(st, "lightning")
        hr = handle_normal_special(st, _key("n"))
        assert st.cursor.row == 6
        assert hr.command_message == "/lightning"

    def test_n_wraps(self) -> None:
        st = _state(row=6)
        st.last_find = "lightning"
        handle_normal_special(st, _key("n"))
        assert st.cursor.row == 5

    def test_shift_n_moves_backward(self) -> None:
        st = _state(row=6)
        st.last_find = "lightning"
        hr = handle_normal_special(st, _key("N"))
        assert st.cursor.row == 5
        assert hr.command_message == "?lightning"

    def test_count_repeats(self) -> None:
        st = _state(row=0)
        st.last_find = "4 "
        handle_normal_special(st, _key("n", 3))
        assert st.cursor.row == 5

    def test_count_with_single_other_match_stops_there(self) -> None:
        st = _state(row=0)
        st.last_find = "charm"
        handle_normal_special(st, _key("n", 5))
        assert st.cursor.row == 7

    def test_no_previous_pattern(self) -> None:
        st = _state(row=2)
        hr = handle_normal_special(st, _key("n"))
        assert hr.error
        assert "No previous search pattern" in hr.command_message
        assert st.cursor.row == 2

    def test_pattern_not_found(self) -> None:
        st = _state(row=2)
        st.last_find = "counterspell"
        hr = handle_normal_special(st, _key("N"))
        assert hr.error
        assert "Pattern not found" in hr.command_message
        assert st.cursor.row == 2


class TestViewMotionsInSession:
    def test_uses_view_band(self) -> None:
        st = _state(row=0)
        st.view_band = (2, 6)
        handle_motion(st, ParsedAction("motion", "L"))
        assert st.cursor.row == 6
        handle_motion(st, ParsedAction("motion", "H"))
        assert st.cursor.row == 2
        handle_motion(st, ParsedAction("motion", "M"))
        # middle row 4 is the Instants header (not blank), so it stays
        assert st.cursor.row == 4

    def test_without_view_whole_buffer_counts(self) -> None:
        st = _state(row=3)
        handle_motion(st, ParsedAction("motion", "H"))
        assert st.cursor.row == 0
        handle_motion(st, ParsedAction("motion", "L"))
        assert st.cursor.row == 7

    def test_count(self) -> None:
        st = _state(row=0)
        st.view_band = (0, 7)
        handle_motion(st, ParsedAction("motion", "L", 2))
        assert st.cursor.row == 6

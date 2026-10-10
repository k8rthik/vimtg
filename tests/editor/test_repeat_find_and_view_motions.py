"""n / N repeat the last / or :find; H / M / L use the deck view's band."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.search_cmds import (
    find_card_row,
    register_search_commands,
)
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


def _registry() -> CommandRegistry:
    reg = CommandRegistry()
    register_search_commands(reg)
    return reg


def _submit(st: EditorState, text: str) -> None:
    handle_command(
        st, ParsedAction("command_submit", "enter", text=text), _registry(), None,
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

    def test_skips_current_and_non_card_lines(self) -> None:
        buf = Buffer.from_text(DECK)
        # "Instants" header matches "i" but is not a card line
        assert find_card_row(buf, 2, "instant") is None
        assert find_card_row(buf, 7, "boros") is None


class TestRepeatFind:
    def test_find_records_pattern(self) -> None:
        st = _state()
        _submit(st, "find lightning")
        assert st.cursor.row == 5
        assert st.last_find == "lightning"

    def test_alias_records_pattern(self) -> None:
        st = _state()
        _submit(st, "f helix")
        assert st.last_find == "helix"

    def test_slash_search_records_pattern(self) -> None:
        st = _state()
        st.mode_mgr.transition(Mode.SEARCH)
        _submit(st, "bolt")
        assert st.cursor.row == 5
        assert st.last_find == "bolt"

    def test_invalid_pattern_not_recorded(self) -> None:
        st = _state()
        _submit(st, "find bolt")
        _submit(st, "find [")
        assert st.last_find == "bolt"

    def test_n_moves_forward(self) -> None:
        st = _state()
        _submit(st, "find lightning")
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

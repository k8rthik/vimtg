"""mi / mo (board in/out) and [v / ]v (plan jumps): keymap + handler."""

from __future__ import annotations

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult, ParsedAction
from vimtg.editor.modes import ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import EditorState, handle_command, handle_normal_special
from vimtg.services.history_service import HistoryService

DECK = (
    "DCK:\n"
    "    4 Lightning Bolt\n"  # 1
    "    2 Skullcrack\n"      # 2
    "\n"
    "SB:\n"
    "    3 Alpine Moon\n"     # 5
    "\n"
    "VS: Tron\n"              # 7
    "    -2 Lightning Bolt\n"  # 8
    "\n"
    "VS: Burn\n"              # 10
)


def _state(text: str = DECK, row: int = 0, active: str | None = None) -> EditorState:
    buffer = Buffer.from_text(text)
    state = EditorState(
        buffer=buffer,
        cursor=Cursor(row=row),
        mode_mgr=ModeManager(),
        registers=RegisterStore(),
        history=HistoryService(),
        modified=False,
        resolved_cards={},
        settings=Settings(),
        active_plan=active,
    )
    state.history.initialize(buffer)
    return state


def _feed(*keys: str) -> ParsedAction:
    km = KeyMap()
    result, action = None, None
    for k in keys:
        result, action = km.feed(k)
    assert result == KeyResult.COMPLETE, keys
    assert action is not None
    return action


class TestKeymap:
    def test_board_keys_are_specials(self) -> None:
        assert _feed("z", "i").action == "zi"
        assert _feed("z", "o").action == "zo"

    def test_board_count_is_raw(self) -> None:
        assert _feed("z", "o").count == 0
        assert _feed("2", "z", "o").count == 2

    def test_plan_jump_keys(self) -> None:
        assert _feed("]", "v").action == "]v"
        assert _feed("[", "v").action == "[v"
        assert _feed("]", "v").action_type == "special"


class TestBoardKeys:
    def test_zo_writes_into_the_active_plan(self) -> None:
        s = _state(row=2, active="Tron")
        hr = handle_normal_special(s, _feed("z", "o"))
        assert s.buffer.get_line(9).text == "    -2 Skullcrack"
        assert s.cursor.row == 2
        assert s.modified
        assert hr.command_message == "vs Tron: -2 Skullcrack  (-4 +0)"
        assert hr.plan_changed

    def test_count_boards_that_many(self) -> None:
        s = _state(row=5, active="Tron")
        handle_normal_special(s, _feed("2", "z", "i"))
        assert s.buffer.get_line(9).text == "    +2 Alpine Moon"

    def test_undo_reverts_a_boarding(self) -> None:
        s = _state(row=2, active="Tron")
        handle_normal_special(s, _feed("z", "o"))
        handle_normal_special(s, _feed("u"))
        assert s.buffer.to_text() == DECK

    def test_dot_repeats_a_boarding(self) -> None:
        s = _state(row=5, active="Tron")
        handle_normal_special(s, _feed("1", "z", "i"))
        handle_normal_special(s, _feed("."))
        assert s.buffer.get_line(9).text == "    +2 Alpine Moon"

    def test_single_plan_is_used_without_activation(self) -> None:
        text = DECK.replace("\nVS: Burn\n", "")
        s = _state(text, row=2)
        hr = handle_normal_special(s, _feed("z", "o"))
        assert not hr.error
        assert s.active_plan == "Tron"
        assert s.buffer.get_line(9).text == "    -2 Skullcrack"

    def test_no_plan_is_an_error(self) -> None:
        s = _state("4 Opt\n")
        hr = handle_normal_special(s, _feed("z", "o"))
        assert hr.error
        assert ":plan <matchup>" in hr.command_message
        assert s.buffer.to_text() == "4 Opt\n"

    def test_ambiguous_plans_need_activation(self) -> None:
        s = _state(row=2)
        hr = handle_normal_special(s, _feed("z", "o"))
        assert hr.error
        assert s.buffer.to_text() == DECK

    def test_boarding_error_leaves_history_alone(self) -> None:
        s = _state(row=8, active="Tron")  # a plan line, not a deck card
        hr = handle_normal_special(s, _feed("z", "o"))
        assert hr.error
        assert s.history.undo() is None

    def test_insert_above_cursor_shifts_the_cursor(self) -> None:
        text = "VS: Tron\n\nDCK:\n    4 Lightning Bolt\n"
        s = _state(text, row=3, active="Tron")
        handle_normal_special(s, _feed("z", "o"))
        assert s.buffer.get_line(1).text == "    -4 Lightning Bolt"
        assert s.cursor.row == 4
        assert s.buffer.card_name_at(4) == "Lightning Bolt"


class TestJumpKeys:
    def test_next_plan_activates_and_moves(self) -> None:
        s = _state(row=0)
        hr = handle_normal_special(s, _feed("]", "v"))
        assert s.cursor.row == 7
        assert s.active_plan == "Tron"
        assert hr.command_message == "vs Tron  -2 +0 !"
        handle_normal_special(s, _feed("]", "v"))
        assert s.active_plan == "Burn"
        assert s.cursor.row == 10

    def test_prev_plan(self) -> None:
        s = _state(row=10)
        handle_normal_special(s, _feed("[", "v"))
        assert s.cursor.row == 7
        assert s.active_plan == "Tron"

    def test_no_further_plan(self) -> None:
        s = _state(row=10)
        hr = handle_normal_special(s, _feed("]", "v"))
        assert s.cursor.row == 10
        assert "No" in hr.command_message


class TestCommandSyncsState:
    def test_plan_command_sets_state(self) -> None:
        from vimtg.editor.command_handlers import register_all_commands
        from vimtg.editor.commands import CommandRegistry

        registry = CommandRegistry()
        register_all_commands(registry)
        s = _state()
        hr = handle_command(
            s, ParsedAction("command_submit", "submit", text="plan burn"),
            registry, None,
        )
        assert s.active_plan == "Burn"
        assert hr.plan_changed
        assert s.cursor.row == 10

"""Tests for the KeyMap key sequence parser."""

from vimtg.editor.keymap import KeyMap, KeyResult
from vimtg.editor.modes import Mode


class TestSimpleMotions:
    def test_simple_motion_j(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("j")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "j"
        assert action.action_type == "motion"
        assert action.count == 1

    def test_simple_motion_k(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("k")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "k"
        assert action.action_type == "motion"

    def test_simple_motion_h(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("h")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "h"

    def test_simple_motion_l(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("l")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "l"

    def test_motion_zero_beginning_of_line(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("0")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "0"

    def test_motion_dollar_end_of_line(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("$")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "$"


class TestCountMotion:
    def test_count_motion(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        r1, a1 = km.feed("4")
        assert r1 == KeyResult.PENDING
        assert a1 is None
        r2, a2 = km.feed("j")
        assert r2 == KeyResult.COMPLETE
        assert a2 is not None
        assert a2.action == "j"
        assert a2.count == 4

    def test_multi_digit_count(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("1")
        km.feed("2")
        result, action = km.feed("k")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.count == 12


class TestModeSwitch:
    def test_mode_switch_i(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("i")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "mode_switch"
        assert action.action == "i"

    def test_mode_switch_a(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("a")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "mode_switch"

    def test_mode_switch_v(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("v")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "mode_switch"
        assert action.action == "v"

    def test_mode_switch_visual_line(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("V")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "mode_switch"
        assert action.action == "V"

    def test_colon_command(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed(":")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "mode_switch"
        assert action.action == ":"

    def test_slash_search(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("/")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "mode_switch"
        assert action.action == "/"


class TestOperatorMotion:
    def test_operator_motion_dj(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        r1, a1 = km.feed("d")
        assert r1 == KeyResult.PENDING
        assert a1 is None
        r2, a2 = km.feed("j")
        assert r2 == KeyResult.COMPLETE
        assert a2 is not None
        assert a2.action_type == "operator"
        assert a2.action == "d"
        assert a2.motion == "j"

    def test_operator_doubled_dd(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("d")
        result, action = km.feed("d")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "dd"
        assert action.action_type == "operator"
        assert action.count == 1

    def test_operator_doubled_yy(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("y")
        result, action = km.feed("y")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "yy"

    def test_operator_count_motion_d3j(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("d")
        km.feed("3")
        result, action = km.feed("j")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "d"
        assert action.motion == "j"
        assert action.count == 3

    def test_count_operator_motion_3dj(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("3")
        km.feed("d")
        result, action = km.feed("j")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "d"
        assert action.motion == "j"
        assert action.count == 3

    def test_count_operator_count_motion(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("2")
        km.feed("d")
        km.feed("3")
        result, action = km.feed("j")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.count == 6  # 2 * 3


class TestRegister:
    def test_register_yank(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed('"')
        km.feed("a")
        km.feed("y")
        result, action = km.feed("y")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.register == "a"
        assert action.action == "yy"

    def test_register_delete(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed('"')
        km.feed("b")
        result, action = km.feed("x")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.register == "b"


class TestMultiKey:
    def test_multi_key_gg(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        r1, a1 = km.feed("g")
        assert r1 == KeyResult.PENDING
        assert a1 is None
        r2, a2 = km.feed("g")
        assert r2 == KeyResult.COMPLETE
        assert a2 is not None
        assert a2.action == "gg"
        assert a2.action_type == "motion"

    def test_multi_key_unknown(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("g")
        result, action = km.feed("x")
        assert result == KeyResult.NO_MATCH
        assert action is None


class TestEscapeResets:
    def test_escape_resets_pending_operator(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("d")
        result, action = km.feed("escape")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "escape"

    def test_escape_resets_count(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("5")
        result, action = km.feed("escape")
        assert result == KeyResult.COMPLETE
        # After escape, state is reset, so next key is fresh
        r2, a2 = km.feed("j")
        assert a2 is not None
        assert a2.count == 1


class TestSpecialKeys:
    def test_special_put(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("p")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "p"
        assert action.action_type == "special"

    def test_special_put_before(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("P")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "P"

    def test_special_undo(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("u")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "u"
        assert action.action_type == "special"

    def test_special_increment(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("+")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "+"
        assert action.action_type == "special"

    def test_special_decrement(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("-")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "-"

    def test_special_delete_char(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("x")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "x"


class TestGMotion:
    def test_goto_last_line_without_count(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("G")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "G"
        assert action.count == 0  # 0 means "last line" (no count given)

    def test_goto_line_with_count(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("5")
        result, action = km.feed("G")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "G"
        assert action.count == 5


class TestInsertMode:
    def test_insert_mode_text_accumulates(self) -> None:
        km = KeyMap(mode=Mode.INSERT)
        _, a1 = km.feed("h")
        assert a1 is not None
        assert a1.text == "h"
        _, a2 = km.feed("e")
        assert a2 is not None
        assert a2.text == "he"
        _, a3 = km.feed("l")
        assert a3 is not None
        assert a3.text == "hel"

    def test_insert_escape_returns_accumulated_text(self) -> None:
        km = KeyMap(mode=Mode.INSERT)
        km.feed("a")
        km.feed("b")
        km.feed("c")
        result, action = km.feed("escape")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "mode_switch"
        assert action.action == "escape"
        assert action.text == "abc"

    def test_insert_backspace(self) -> None:
        km = KeyMap(mode=Mode.INSERT)
        km.feed("a")
        km.feed("b")
        _, action = km.feed("backspace")
        assert action is not None
        assert action.action == "backspace"
        assert action.text == "a"

    def test_insert_special_keys(self) -> None:
        km = KeyMap(mode=Mode.INSERT)
        result, action = km.feed("tab")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "tab"


class TestCommandMode:
    def test_command_mode_text_accumulates(self) -> None:
        km = KeyMap(mode=Mode.COMMAND)
        km.feed("w")
        _, action = km.feed("q")
        assert action is not None
        assert action.text == "wq"

    def test_command_enter_submits(self) -> None:
        km = KeyMap(mode=Mode.COMMAND)
        km.feed("w")
        km.feed("q")
        result, action = km.feed("enter")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "command_submit"
        assert action.action == "enter"
        assert action.text == "wq"

    def test_command_escape_cancels(self) -> None:
        km = KeyMap(mode=Mode.COMMAND)
        km.feed("w")
        result, action = km.feed("escape")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "mode_switch"
        assert action.action == "escape"

    def test_command_backspace(self) -> None:
        km = KeyMap(mode=Mode.COMMAND)
        km.feed("a")
        km.feed("b")
        _, action = km.feed("backspace")
        assert action is not None
        assert action.text == "a"

    def test_command_tab_completion(self) -> None:
        km = KeyMap(mode=Mode.COMMAND)
        km.feed("w")
        result, action = km.feed("tab")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "tab"
        assert action.text == "w"


class TestVisualMode:
    def test_visual_operator_d(self) -> None:
        km = KeyMap(mode=Mode.VISUAL)
        result, action = km.feed("d")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "operator"
        assert action.action == "d"

    def test_visual_operator_y(self) -> None:
        km = KeyMap(mode=Mode.VISUAL)
        result, action = km.feed("y")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "operator"
        assert action.action == "y"

    def test_visual_motion_extends_selection(self) -> None:
        km = KeyMap(mode=Mode.VISUAL)
        result, action = km.feed("j")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "motion"
        assert action.action == "j"

    def test_visual_escape(self) -> None:
        km = KeyMap(mode=Mode.VISUAL)
        result, action = km.feed("escape")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "mode_switch"

    def test_visual_colon_enters_command(self) -> None:
        km = KeyMap(mode=Mode.VISUAL)
        result, action = km.feed(":")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "mode_switch"
        assert action.action == ":"


class TestNoMatch:
    def test_unknown_key(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        result, action = km.feed("Z")
        assert result == KeyResult.NO_MATCH
        assert action is None


class TestSetMode:
    def test_set_mode_resets_state(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed("d")  # pending operator
        km.set_mode(Mode.INSERT)
        # Now in insert mode, "d" should be a character
        result, action = km.feed("d")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.text == "d"

    def test_reset_text_clears_accumulated(self) -> None:
        km = KeyMap(mode=Mode.INSERT)
        km.feed("a")
        km.feed("b")
        km.reset_text()
        _, action = km.feed("c")
        assert action is not None
        assert action.text == "c"

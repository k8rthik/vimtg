"""Comprehensive tests for key translation and end-to-end keybind verification.

These tests verify that EVERY keybind vimtg advertises actually works when
a Textual key event arrives. If you add a new keybind, add a test here.
If this test fails, the keybind is broken for users.
"""

import pytest

from vimtg.tui.key_translator import translate


class TestSymbolTranslation:
    """Verify all punctuation keys Textual sends as verbose names."""

    @pytest.mark.parametrize(
        "textual_key, expected",
        [
            ("colon", ":"),
            ("slash", "/"),
            ("plus", "+"),
            ("minus", "-"),
            ("dollar_sign", "$"),
            ("question_mark", "?"),
            ("left_curly_bracket", "{"),
            ("right_curly_bracket", "}"),
            ("left_square_bracket", "["),
            ("right_square_bracket", "]"),
            ("quotation_mark", '"'),
            ("apostrophe", "'"),
            ("full_stop", "."),
            ("at", "@"),
            ("exclamation_mark", "!"),
            ("underscore", "_"),
            ("tilde", "~"),
            ("grave_accent", "`"),
            ("asterisk", "*"),
            ("ampersand", "&"),
            ("circumflex_accent", "^"),
            ("vertical_line", "|"),
            ("less_than_sign", "<"),
            ("greater_than_sign", ">"),
            ("comma", ","),
            ("semicolon", ";"),
            ("equals_sign", "="),
            ("percent_sign", "%"),
            ("number_sign", "#"),
            ("backslash", "\\"),
            ("left_parenthesis", "("),
            ("right_parenthesis", ")"),
            ("space", " "),
        ],
    )
    def test_symbol_translation(self, textual_key: str, expected: str) -> None:
        assert translate(textual_key) == expected


class TestModifierTranslation:
    """Verify Textual's ctrl+x format maps to our ctrl_x format."""

    @pytest.mark.parametrize(
        "textual_key, expected",
        [
            ("ctrl+c", "ctrl_c"),
            ("ctrl+r", "ctrl_r"),
            ("ctrl+d", "ctrl_d"),
            ("ctrl+u", "ctrl_u"),
            ("ctrl+j", "ctrl_j"),
            ("ctrl+k", "ctrl_k"),
            ("ctrl+n", "ctrl_n"),
            ("ctrl+p", "ctrl_p"),
            ("shift+tab", "shift_tab"),
        ],
    )
    def test_modifier_translation(self, textual_key: str, expected: str) -> None:
        assert translate(textual_key) == expected


class TestPassthrough:
    """Verify keys that should pass through unchanged."""

    @pytest.mark.parametrize(
        "key",
        ["j", "k", "h", "l", "w", "b", "i", "a", "o", "O", "A",
         "v", "V", "d", "y", "c", "p", "P", "x", "u", "G", "g",
         "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
         "escape", "enter", "backspace", "tab",
         "left", "right", "home", "end", "delete"],
    )
    def test_passthrough(self, key: str) -> None:
        assert translate(key) == key


class TestEndToEndKeybinds:
    """Verify that every advertised keybind produces the correct KeyMap action.

    This tests the FULL pipeline: Textual key name → translate → KeyMap → action.
    If you add a keybind to vimtg, add a test case here.
    """

    def _feed(self, *textual_keys: str) -> tuple:
        """Feed keys through translate + KeyMap and return the final result."""
        from vimtg.editor.keymap import KeyMap
        from vimtg.editor.modes import Mode

        km = KeyMap(mode=Mode.NORMAL)
        result = None
        action = None
        for tk in textual_keys:
            key = translate(tk)
            result, action = km.feed(key)
        return result, action

    def _feed_insert(self, *textual_keys: str) -> tuple:
        from vimtg.editor.keymap import KeyMap
        from vimtg.editor.modes import Mode

        km = KeyMap(mode=Mode.INSERT)
        result = action = None
        for tk in textual_keys:
            result, action = km.feed(translate(tk))
        return result, action

    def _feed_command(self, *textual_keys: str) -> tuple:
        from vimtg.editor.keymap import KeyMap
        from vimtg.editor.modes import Mode

        km = KeyMap(mode=Mode.COMMAND)
        result = action = None
        for tk in textual_keys:
            result, action = km.feed(translate(tk))
        return result, action

    # -- NORMAL mode motions --

    @pytest.mark.parametrize(
        "keys, expected_action",
        [
            (["j"], "j"),
            (["k"], "k"),
            (["h"], "h"),
            (["l"], "l"),
            (["w"], "w"),
            (["b"], "b"),
            (["left_curly_bracket"], "{"),
            (["right_curly_bracket"], "}"),
            (["dollar_sign"], "$"),
            (["0"], "0"),
            (["g", "g"], "gg"),
            (["G"], "G"),
            (["left_square_bracket", "left_square_bracket"], "[["),
            (["right_square_bracket", "right_square_bracket"], "]]"),
        ],
    )
    def test_normal_motion(self, keys: list[str], expected_action: str) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed(*keys)
        assert result == KeyResult.COMPLETE, f"Keys {keys} did not complete"
        assert action is not None
        assert action.action == expected_action

    # -- NORMAL mode switches --

    @pytest.mark.parametrize(
        "keys, expected_action",
        [
            (["o"], "o"),
            (["O"], "O"),
            (["colon"], ":"),
            (["slash"], "/"),
            (["v"], "v"),
            (["V"], "V"),
        ],
    )
    def test_normal_mode_switch(self, keys: list[str], expected_action: str) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed(*keys)
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action_type == "mode_switch"
        assert action.action == expected_action

    # -- NORMAL mode specials --

    @pytest.mark.parametrize(
        "keys, expected_action",
        [
            (["p"], "p"),
            (["P"], "P"),
            (["x"], "x"),
            (["u"], "u"),
            (["plus"], "+"),
            (["minus"], "-"),
            (["full_stop"], "."),
            (["question_mark"], "?"),
            (["at"], "@"),
        ],
    )
    def test_normal_special(self, keys: list[str], expected_action: str) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed(*keys)
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == expected_action

    # -- Operators --

    def test_operator_dd(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed("d", "d")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "dd"

    def test_operator_yy(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed("y", "y")
        assert result == KeyResult.COMPLETE
        assert action.action == "yy"

    def test_operator_dw(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed("d", "w")
        assert result == KeyResult.COMPLETE
        assert action.action == "d"
        assert action.motion == "w"

    def test_operator_d_section(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed("d", "right_curly_bracket")
        assert result == KeyResult.COMPLETE
        assert action.action == "d"
        assert action.motion == "}"

    # -- INSERT mode --

    def test_insert_typing(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed_insert("l", "i", "g")
        assert result == KeyResult.COMPLETE
        assert action.text == "lig"

    def test_insert_space(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed_insert("h", "i", "space", "m", "o", "m")
        assert result == KeyResult.COMPLETE
        assert action.text == "hi mom"

    def test_insert_escape(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed_insert("escape")
        assert result == KeyResult.COMPLETE
        assert action.action == "escape"

    # -- COMMAND mode --

    def test_command_typing(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed_command("w")
        assert result == KeyResult.COMPLETE
        assert action.text == "w"

    def test_command_space(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed_command("e", "space", "f")
        assert result == KeyResult.COMPLETE
        assert action.text == "e f"

    def test_command_enter(self) -> None:
        from vimtg.editor.keymap import KeyResult

        km = self._make_command_km()
        km.feed(translate("s"))
        km.feed(translate("o"))
        km.feed(translate("r"))
        km.feed(translate("t"))
        result, action = km.feed(translate("enter"))
        assert result == KeyResult.COMPLETE
        assert action.action_type == "command_submit"
        assert action.text == "sort"

    def _make_command_km(self):
        from vimtg.editor.keymap import KeyMap
        from vimtg.editor.modes import Mode

        return KeyMap(mode=Mode.COMMAND)

    # -- Count prefixes --

    def test_count_motion(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed("3", "j")
        assert result == KeyResult.COMPLETE
        assert action.count == 3
        assert action.action == "j"

    def test_count_operator(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed("3", "d", "d")
        assert result == KeyResult.COMPLETE
        assert action.count == 3

    # -- Cursor movement in INSERT mode --

    def test_insert_left_right(self) -> None:
        from vimtg.editor.keymap import KeyResult

        result, action = self._feed_insert("a", "b", "left")
        assert result == KeyResult.COMPLETE
        assert action.action == "cursor_move"
        assert action.cursor_pos == 1

    def test_insert_home_end(self) -> None:
        from vimtg.editor.keymap import KeyResult

        _, action = self._feed_insert("a", "b", "home")
        assert action.cursor_pos == 0
        # Can't test end directly since we need a fresh km with cursor at 0

    def test_insert_delete_key(self) -> None:
        from vimtg.editor.keymap import KeyResult

        _, action = self._feed_insert("a", "b", "home", "delete")
        assert action.action == "delete"
        assert action.text == "b"

    # -- Cursor movement in COMMAND mode --

    def test_command_left_right(self) -> None:
        from vimtg.editor.keymap import KeyResult

        _, action = self._feed_command("s", "o", "left")
        assert action.action == "cursor_move"
        assert action.cursor_pos == 1

    def test_command_shift_tab(self) -> None:
        from vimtg.editor.keymap import KeyResult

        _, action = self._feed_command("s", "shift+tab")
        assert action.action == "shift_tab"

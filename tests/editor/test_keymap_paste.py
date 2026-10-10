"""KeyMap.paste: a terminal paste lands in the active text line at once."""

from __future__ import annotations

from vimtg.editor.keymap import KeyMap
from vimtg.editor.modes import Mode


def test_paste_inserts_at_insert_cursor() -> None:
    km = KeyMap(Mode.INSERT)
    for key in ("a", "b", "left"):
        km.feed(key)
    action = km.paste("XY")
    assert action is not None
    assert (action.action, action.text, action.cursor_pos) == ("char", "aXYb", 3)
    # Typing continues from after the pasted text
    _, typed = km.feed("z")
    assert typed is not None and typed.text == "aXYzb"


def test_paste_into_command_line() -> None:
    km = KeyMap(Mode.COMMAND)
    km.feed("w")
    action = km.paste(" deck.deck")
    assert action is not None and action.text == "w deck.deck"
    _, submit = km.feed("enter")
    assert submit is not None and submit.text == "w deck.deck"


def test_paste_ignored_in_normal_mode() -> None:
    assert KeyMap(Mode.NORMAL).paste("4 Lightning Bolt") is None

"""Ex command fidelity: relative addresses, vim's E492 for an unknown
command, and the removed commands that answer it."""

from __future__ import annotations

import pytest

from tests.editor.test_vim_fidelity import _ex, _state
from vimtg.editor.commands import CommandRange, parse_command

# Rows (0-based), as in test_vim_fidelity:
#  0 // Creature   4 // Instant         8 // Land
#  1 4 Goblin      5 4 Lightning Bolt   9 20 Mountain
#  2 4 Swiftspear  6 4 Searing Blaze
#  3 (blank)       7 (blank)


class TestRelativeAddresses:
    @pytest.mark.parametrize(("text", "start", "end"), [
        (".+1", 6, 6), ("+3", 8, 8), ("-2", 3, 3), ("+", 6, 6), ("-", 4, 4),
        (".,+3", 5, 8), ("-1,.", 4, 5), ("$-1", 8, 8), ("3+2", 4, 4), ("'a+1", 3, 3),
    ])
    def test_offsets_count_from_their_base(self, text: str, start: int, end: int) -> None:
        cmd = parse_command(f"{text}sort", cursor_row=5, line_count=10, marks={"a": 2})
        assert cmd.name == "sort"
        assert cmd.cmd_range == CommandRange(start=start, end=end)

    def test_a_bare_offset_moves_the_cursor(self) -> None:
        state = _state(row=1)
        _ex(state, "+3")
        assert state.cursor.row == 4


class TestUnknownCommand:
    def test_it_is_e492_with_the_text(self) -> None:
        state = _state()
        assert _ex(state, "frobnicate now") == "E492: Not an editor command: frobnicate now"
        assert _ex(state, "nope!") == "E492: Not an editor command: nope!"

    @pytest.mark.parametrize("line", ["tag core", "untag core", "tags", "retag /a/b/"])
    def test_card_tag_commands_are_gone(self, line: str) -> None:
        state = _state()
        assert _ex(state, line) == f"E492: Not an editor command: {line}"

    @pytest.mark.parametrize("line", [
        "d", "delete", "y", "yank", "m 0", "move 0", "t 0", "co 0", "copy 0",
        "undo", "u", "redo", "red", "find Bolt", "f Bolt", "search bolt",
        "noh", "nohlsearch", "qa", "qall", "quitall", "wa", "wall",
        "wqa", "wqall", "xa", "xall", "stats",
    ])
    def test_ex_mirrors_of_normal_keys_are_gone(self, line: str) -> None:
        """dd yy p u Ctrl-R / o :q :w cover these; one buffer needs no :qa."""
        state = _state()
        assert _ex(state, line) == f"E492: Not an editor command: {line}"

    def test_sort_by_tag_is_an_unknown_field(self) -> None:
        state = _state()
        assert _ex(state, "sort tag") == "E: Unknown sort field: tag"

"""Ex command fidelity: relative addresses, :d / :y counts, :noh, and
vim's E492 for an unknown command."""

from __future__ import annotations

import pytest

from tests.editor.test_vim_fidelity import _ex, _state, _texts
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
        cmd = parse_command(f"{text}d", cursor_row=5, line_count=10, marks={"a": 2})
        assert cmd.name == "d"
        assert cmd.cmd_range == CommandRange(start=start, end=end)

    def test_a_bare_offset_moves_the_cursor(self) -> None:
        state = _state(row=1)
        _ex(state, "+3")
        assert state.cursor.row == 4

    def test_dot_comma_plus_deletes_a_span(self) -> None:
        state = _state(row=5)
        _ex(state, ".,+1d")
        assert "4 Lightning Bolt" not in _texts(state.buffer)
        assert "4 Searing Blaze" not in _texts(state.buffer)

    def test_move_down_and_up_by_offset(self) -> None:
        state = _state(row=1)
        _ex(state, "m+1")
        assert _texts(state.buffer)[1:3] == ["4 Monastery Swiftspear", "4 Goblin Guide"]
        _ex(state, "m-2")
        assert _texts(state.buffer)[1:3] == ["4 Goblin Guide", "4 Monastery Swiftspear"]

    def test_copy_above_by_offset(self) -> None:
        state = _state(row=6)
        _ex(state, "t-1")
        assert _texts(state.buffer)[5:8] == [
            "4 Lightning Bolt", "4 Searing Blaze", "4 Searing Blaze",
        ]


class TestDeleteYankCounts:
    def test_a_bare_number_is_a_count(self) -> None:
        state = _state(row=1)
        _ex(state, "d 2")
        assert "4 Goblin Guide" not in _texts(state.buffer)
        assert "4 Monastery Swiftspear" not in _texts(state.buffer)
        assert state.registers.get('"').content == (
            "4 Goblin Guide", "4 Monastery Swiftspear",
        )

    def test_register_and_count(self) -> None:
        state = _state(row=5)
        _ex(state, "y a 2")
        assert state.registers.get("a").content == ("4 Lightning Bolt", "4 Searing Blaze")

    def test_the_count_starts_at_the_end_of_the_range(self) -> None:
        state = _state(row=0)
        _ex(state, "2,5y 2")  # vim: lines 5-6 (1-based)
        assert state.registers.get('"').content == ("// Instant", "4 Lightning Bolt")

    def test_trailing_garbage_is_still_refused(self) -> None:
        state = _state(row=1)
        assert "E488" in _ex(state, "d a b")


class TestNoh:
    @pytest.mark.parametrize("name", ["noh", "nohlsearch"])
    def test_noh_is_accepted(self, name: str) -> None:
        state = _state()
        assert _ex(state, name) == ""


class TestUnknownCommand:
    def test_it_is_e492_with_the_text(self) -> None:
        state = _state()
        assert _ex(state, "frobnicate now") == "E492: Not an editor command: frobnicate now"
        assert _ex(state, "nope!") == "E492: Not an editor command: nope!"

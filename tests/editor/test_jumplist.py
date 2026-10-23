"""The jumplist Ctrl-O / Ctrl-I walk."""

from __future__ import annotations

from vimtg.editor.jumplist import MAX_JUMPS, JumpList


def test_back_then_forward_returns_to_where_the_walk_started() -> None:
    jumps = JumpList().jump(3).jump(10)
    jumps, row = jumps.back(current=20)
    assert row == 10
    jumps, row = jumps.back(current=10)
    assert row == 3
    jumps, row = jumps.back(current=3)
    assert row is None
    jumps, row = jumps.forward()
    assert row == 10
    jumps, row = jumps.forward()
    assert row == 20
    assert jumps.forward()[1] is None


def test_counts_skip_entries() -> None:
    jumps = JumpList().jump(1).jump(2).jump(3)
    jumps, row = jumps.back(current=4, count=2)
    assert row == 2
    assert jumps.forward(count=2)[1] == 4


def test_a_row_appears_once_at_its_newest_place() -> None:
    jumps = JumpList().jump(3).jump(10).jump(3)
    assert jumps.rows == (10, 3)


def test_a_jump_while_walking_appends_and_restarts() -> None:
    jumps = JumpList().jump(1).jump(2)
    jumps, _ = jumps.back(current=5)
    jumps = jumps.jump(7)
    assert jumps.rows == (1, 2, 5, 7) and jumps.index == 4
    assert jumps.back(current=9)[1] == 7


def test_the_list_is_bounded() -> None:
    jumps = JumpList()
    for row in range(MAX_JUMPS + 5):
        jumps = jumps.jump(row)
    assert len(jumps.rows) == MAX_JUMPS and jumps.rows[-1] == MAX_JUMPS + 4

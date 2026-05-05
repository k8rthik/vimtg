"""Tests for LineBuffer — immutable cursor-aware text buffer."""

from vimtg.editor.line_buffer import LineBuffer


class TestInsert:
    def test_insert_into_empty(self) -> None:
        buf = LineBuffer()
        result = buf.insert("a")
        assert result.text == "a"
        assert result.cursor == 1

    def test_insert_at_end(self) -> None:
        buf = LineBuffer("ab", 2)
        result = buf.insert("c")
        assert result.text == "abc"
        assert result.cursor == 3

    def test_insert_at_beginning(self) -> None:
        buf = LineBuffer("bc", 0)
        result = buf.insert("a")
        assert result.text == "abc"
        assert result.cursor == 1

    def test_insert_in_middle(self) -> None:
        buf = LineBuffer("ac", 1)
        result = buf.insert("b")
        assert result.text == "abc"
        assert result.cursor == 2

    def test_insert_multi_char(self) -> None:
        buf = LineBuffer("ac", 1)
        result = buf.insert("XY")
        assert result.text == "aXYc"
        assert result.cursor == 3

    def test_original_unchanged(self) -> None:
        buf = LineBuffer("ab", 1)
        buf.insert("X")
        assert buf.text == "ab"
        assert buf.cursor == 1


class TestDeleteBackward:
    def test_delete_backward_at_end(self) -> None:
        buf = LineBuffer("abc", 3)
        result = buf.delete_backward()
        assert result.text == "ab"
        assert result.cursor == 2

    def test_delete_backward_in_middle(self) -> None:
        buf = LineBuffer("abc", 2)
        result = buf.delete_backward()
        assert result.text == "ac"
        assert result.cursor == 1

    def test_delete_backward_at_beginning_noop(self) -> None:
        buf = LineBuffer("abc", 0)
        result = buf.delete_backward()
        assert result is buf  # same instance — no change

    def test_delete_backward_single_char(self) -> None:
        buf = LineBuffer("a", 1)
        result = buf.delete_backward()
        assert result.text == ""
        assert result.cursor == 0


class TestDeleteForward:
    def test_delete_forward_at_beginning(self) -> None:
        buf = LineBuffer("abc", 0)
        result = buf.delete_forward()
        assert result.text == "bc"
        assert result.cursor == 0

    def test_delete_forward_in_middle(self) -> None:
        buf = LineBuffer("abc", 1)
        result = buf.delete_forward()
        assert result.text == "ac"
        assert result.cursor == 1

    def test_delete_forward_at_end_noop(self) -> None:
        buf = LineBuffer("abc", 3)
        result = buf.delete_forward()
        assert result is buf  # same instance — no change

    def test_delete_forward_single_char(self) -> None:
        buf = LineBuffer("a", 0)
        result = buf.delete_forward()
        assert result.text == ""
        assert result.cursor == 0


class TestMoveLeft:
    def test_move_left(self) -> None:
        buf = LineBuffer("abc", 2)
        result = buf.move_left()
        assert result.text == "abc"
        assert result.cursor == 1

    def test_move_left_at_beginning_noop(self) -> None:
        buf = LineBuffer("abc", 0)
        result = buf.move_left()
        assert result is buf


class TestMoveRight:
    def test_move_right(self) -> None:
        buf = LineBuffer("abc", 1)
        result = buf.move_right()
        assert result.text == "abc"
        assert result.cursor == 2

    def test_move_right_at_end_noop(self) -> None:
        buf = LineBuffer("abc", 3)
        result = buf.move_right()
        assert result is buf


class TestMoveHome:
    def test_move_home(self) -> None:
        buf = LineBuffer("abc", 2)
        result = buf.move_home()
        assert result.text == "abc"
        assert result.cursor == 0

    def test_move_home_already_at_beginning_noop(self) -> None:
        buf = LineBuffer("abc", 0)
        result = buf.move_home()
        assert result is buf


class TestMoveEnd:
    def test_move_end(self) -> None:
        buf = LineBuffer("abc", 1)
        result = buf.move_end()
        assert result.text == "abc"
        assert result.cursor == 3

    def test_move_end_already_at_end_noop(self) -> None:
        buf = LineBuffer("abc", 3)
        result = buf.move_end()
        assert result is buf


class TestFromText:
    def test_from_text_cursor_at_end(self) -> None:
        buf = LineBuffer.from_text("hello")
        assert buf.text == "hello"
        assert buf.cursor == 5

    def test_from_text_empty(self) -> None:
        buf = LineBuffer.from_text("")
        assert buf.text == ""
        assert buf.cursor == 0


class TestCursorAtEnd:
    def test_cursor_at_end_true(self) -> None:
        buf = LineBuffer("abc", 3)
        assert buf.cursor_at_end is True

    def test_cursor_at_end_false(self) -> None:
        buf = LineBuffer("abc", 1)
        assert buf.cursor_at_end is False

    def test_empty_buffer_cursor_at_end(self) -> None:
        buf = LineBuffer()
        assert buf.cursor_at_end is True

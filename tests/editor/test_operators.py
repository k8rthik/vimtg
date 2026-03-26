"""Tests for vimtg.editor.operators — vim-style operators."""

from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.operators import (
    decrement_quantity,
    execute_operator,
    increment_quantity,
    put_lines,
)
from vimtg.editor.registers import RegisterStore

SAMPLE_DECK = """\
// Creature
4 Ragavan, Nimble Pilferer
2 Dragon's Rage Channeler
// Instant
4 Lightning Bolt
3 Unholy Heat
SB: 2 Engineered Explosives"""


def _make_buffer() -> Buffer:
    return Buffer.from_text(SAMPLE_DECK)


def _make_cursor(row: int = 0, col: int = 0) -> Cursor:
    return Cursor(row=row, col=col)


class TestDeleteOperator:
    def test_delete_line_dd(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=1)  # "4 Ragavan..."
        regs = RegisterStore()
        result = execute_operator("dd", None, cursor, buf, 1, regs)
        assert result.buffer.line_count() == buf.line_count() - 1
        assert result.registers.get('"').content == ("4 Ragavan, Nimble Pilferer",)
        # Cursor stays at row 1
        assert result.cursor.row == 1

    def test_delete_range_d3j(self) -> None:
        """d3j should delete from cursor row through 3 lines down (4 lines total)."""
        buf = _make_buffer()
        cursor = _make_cursor(row=1)  # "4 Ragavan..."
        regs = RegisterStore()
        result = execute_operator("d", "j", cursor, buf, 3, regs)
        # Lines 1-4 deleted (cursor.row=1, motion j count=3 -> row 4)
        assert result.buffer.line_count() == buf.line_count() - 4
        deleted = result.registers.get('"').content
        assert len(deleted) == 4

    def test_delete_numbered_register_shift(self) -> None:
        buf = _make_buffer()
        regs = RegisterStore()
        r1 = execute_operator("dd", None, _make_cursor(row=1), buf, 1, regs)
        # Second delete should shift previous to register 2
        r2 = execute_operator(
            "dd", None, _make_cursor(row=1), r1.buffer, 1, r1.registers
        )
        assert r2.registers.get("1").content != r1.registers.get("1").content


class TestYankOperator:
    def test_yank_line_yy(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=1)
        regs = RegisterStore()
        result = execute_operator("yy", None, cursor, buf, 1, regs)
        # Buffer unchanged
        assert result.buffer.line_count() == buf.line_count()
        assert result.registers.get('"').content == ("4 Ragavan, Nimble Pilferer",)

    def test_yank_to_named_register(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=1)
        regs = RegisterStore()
        result = execute_operator("yy", None, cursor, buf, 1, regs, register_name="a")
        assert result.registers.get("a").content == ("4 Ragavan, Nimble Pilferer",)

    def test_yank_stores_in_zero_register(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=1)
        regs = RegisterStore()
        result = execute_operator("yy", None, cursor, buf, 1, regs)
        assert result.registers.get("0").content == ("4 Ragavan, Nimble Pilferer",)


class TestChangeOperator:
    def test_change_enters_insert(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=1)
        regs = RegisterStore()
        result = execute_operator("cc", None, cursor, buf, 1, regs)
        assert result.enter_insert is True

    def test_change_deletes_line(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=1)
        regs = RegisterStore()
        result = execute_operator("cc", None, cursor, buf, 1, regs)
        assert result.buffer.line_count() == buf.line_count() - 1
        assert result.registers.get('"').content == ("4 Ragavan, Nimble Pilferer",)


class TestOperatorWithMotion:
    def test_d_with_j_motion(self) -> None:
        """dj should delete current line and line below (2 lines)."""
        buf = _make_buffer()
        cursor = _make_cursor(row=1)
        regs = RegisterStore()
        result = execute_operator("d", "j", cursor, buf, 1, regs)
        assert result.buffer.line_count() == buf.line_count() - 2

    def test_y_with_k_motion(self) -> None:
        """yk should yank current line and line above (2 lines)."""
        buf = _make_buffer()
        cursor = _make_cursor(row=2)
        regs = RegisterStore()
        result = execute_operator("y", "k", cursor, buf, 1, regs)
        assert len(result.registers.get('"').content) == 2
        assert result.buffer.line_count() == buf.line_count()  # buffer unchanged


class TestPutLines:
    def test_put_below(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=1)
        regs = RegisterStore().set('"', ("3 Murktide Regent",))
        new_buf, new_cur = put_lines(buf, cursor, regs)
        assert new_buf.line_count() == buf.line_count() + 1
        assert new_buf.get_line(2).text == "3 Murktide Regent"
        assert new_cur.row == 2

    def test_put_above(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=1)
        regs = RegisterStore().set('"', ("3 Murktide Regent",))
        new_buf, new_cur = put_lines(buf, cursor, regs, above=True)
        assert new_buf.line_count() == buf.line_count() + 1
        assert new_buf.get_line(1).text == "3 Murktide Regent"
        assert new_cur.row == 1

    def test_put_empty_register_noop(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=0)
        regs = RegisterStore()
        new_buf, new_cur = put_lines(buf, cursor, regs)
        assert new_buf.line_count() == buf.line_count()
        assert new_cur == cursor

    def test_put_multiple_lines(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=0)
        regs = RegisterStore().set('"', ("1 Card A", "2 Card B"))
        new_buf, _ = put_lines(buf, cursor, regs)
        assert new_buf.line_count() == buf.line_count() + 2
        assert new_buf.get_line(1).text == "1 Card A"
        assert new_buf.get_line(2).text == "2 Card B"


class TestIncrementQuantity:
    def test_increment_card(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=1)  # "4 Ragavan..."
        new_buf = increment_quantity(buf, cursor)
        assert new_buf.get_line(1).text == "5 Ragavan, Nimble Pilferer"

    def test_increment_sideboard(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=6)  # "SB: 2 Engineered Explosives"
        new_buf = increment_quantity(buf, cursor)
        assert new_buf.get_line(6).text == "SB: 3 Engineered Explosives"

    def test_increment_on_comment_noop(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=0)  # "// Creature"
        new_buf = increment_quantity(buf, cursor)
        assert new_buf.get_line(0).text == buf.get_line(0).text


class TestDecrementQuantity:
    def test_decrement_card(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=1)  # "4 Ragavan..."
        new_buf, _ = decrement_quantity(buf, cursor)
        assert new_buf.get_line(1).text == "3 Ragavan, Nimble Pilferer"

    def test_decrement_to_zero_deletes(self) -> None:
        # Create a buffer with a 1-count card
        buf = Buffer.from_text("// Deck\n1 Solo Card\n4 Other Card")
        cursor = _make_cursor(row=1)
        new_buf, new_cur = decrement_quantity(buf, cursor)
        assert new_buf.line_count() == 2  # line was removed
        assert new_buf.get_line(1).text == "4 Other Card"

    def test_decrement_on_comment_noop(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=0)
        new_buf, new_cur = decrement_quantity(buf, cursor)
        assert new_buf.get_line(0).text == buf.get_line(0).text
        assert new_cur == cursor

    def test_decrement_sideboard(self) -> None:
        buf = _make_buffer()
        cursor = _make_cursor(row=6)  # "SB: 2 Engineered Explosives"
        new_buf, _ = decrement_quantity(buf, cursor)
        assert new_buf.get_line(6).text == "SB: 1 Engineered Explosives"

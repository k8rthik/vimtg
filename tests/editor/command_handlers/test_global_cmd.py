"""Tests for the :g and :v global command handlers."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.global_cmd import cmd_global
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _make_cmd(
    name: str = "g",
    args: str = "",
) -> ParsedCommand:
    return ParsedCommand(name=name, args=args)


def _line_texts(buffer: Buffer) -> list[str]:
    return [bl.text for bl in buffer.get_lines()]


class TestGlobalDelete:
    def test_global_delete(self) -> None:
        """:g/Bolt/d removes matching card lines."""
        text = "4 Lightning Bolt\n2 Counterspell\n1 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, new_cur = cmd_global(
            buffer, cursor, _make_cmd(args="/Bolt/d"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines == ["2 Counterspell"]
        assert "2 lines deleted" in ctx.message
        assert ctx.modified is True

    def test_global_multiple_matches(self) -> None:
        """All matching lines are deleted, not just the first."""
        text = (
            "4 Lightning Bolt\n"
            "2 Counterspell\n"
            "3 Shock\n"
            "1 Lightning Helix\n"
        )
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Lightning/d"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines == ["2 Counterspell", "3 Shock"]
        assert "2 lines deleted" in ctx.message

    def test_global_single_match(self) -> None:
        """Deleting a single matching line works."""
        text = "4 Lightning Bolt\n2 Counterspell\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Counterspell/d"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines == ["4 Lightning Bolt"]
        assert "1 lines deleted" in ctx.message


class TestGlobalInverse:
    def test_global_inverse_delete(self) -> None:
        """:v/SB:/d removes card lines NOT matching SB: prefix."""
        text = "4 Lightning Bolt\nSB: 2 Negate\n3 Shock\nSB: 1 Dispel\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(name="v", args="/SB:/d"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines == ["SB: 2 Negate", "SB: 1 Dispel"]
        assert "2 lines deleted" in ctx.message


class TestGlobalNoMatch:
    def test_global_no_match(self) -> None:
        """No matches produces informational message."""
        text = "4 Lightning Bolt\n2 Counterspell\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Nonexistent/d"), ctx
        )
        assert "Pattern not found" in ctx.message
        # Buffer unchanged
        assert _line_texts(new_buf) == ["4 Lightning Bolt", "2 Counterspell"]


class TestGlobalInvalidPattern:
    def test_global_invalid_regex(self) -> None:
        """Invalid regex produces error message."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/[invalid/d"), ctx
        )
        assert "E: Invalid pattern" in ctx.message
        assert ctx.error is True


class TestGlobalMissingCommand:
    def test_global_missing_subcommand(self) -> None:
        """Missing sub-command after pattern produces error."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Bolt/"), ctx
        )
        assert "E: Usage" in ctx.message
        assert ctx.error is True

    def test_global_too_short_args(self) -> None:
        """Args too short to parse produces error."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args=""), ctx
        )
        assert "E: Usage" in ctx.message


class TestGlobalPreservesComments:
    def test_global_preserves_comments(self) -> None:
        """Only card lines are matched; comments are preserved."""
        text = (
            "// Creatures\n"
            "4 Lightning Bolt\n"
            "2 Counterspell\n"
            "// Bolt is great\n"
        )
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Bolt/d"), ctx
        )
        lines = _line_texts(new_buf)
        # Comment lines with "Bolt" are NOT deleted
        assert "// Creatures" in lines
        assert "// Bolt is great" in lines
        assert "2 Counterspell" in lines
        assert "1 lines deleted" in ctx.message

    def test_global_unsupported_subcommand(self) -> None:
        """Unsupported sub-command produces error."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Bolt/m0"), ctx
        )
        assert "E: Unsupported sub-command" in ctx.message
        assert ctx.error is True


class TestGlobalCursorAdjustment:
    def test_cursor_adjusts_after_delete(self) -> None:
        """Cursor row is clamped to valid range after lines are deleted."""
        text = "4 Lightning Bolt\n2 Counterspell\n3 Shock\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=2)  # On last line
        ctx = EditorContext()

        # Delete last two lines (Counterspell, Shock)
        new_buf, new_cur = cmd_global(
            buffer, cursor, _make_cmd(args="/spell|Shock/d"), ctx
        )
        assert new_cur.row <= new_buf.line_count() - 1
        assert new_cur.row >= 0

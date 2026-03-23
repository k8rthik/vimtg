"""Tests for the :find search command handler."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.search_cmds import cmd_find
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _make_cmd(args: str = "") -> ParsedCommand:
    return ParsedCommand(name="find", args=args)


class TestFindForward:
    def test_find_forward(self) -> None:
        """:find jumps to the next matching card line."""
        text = "4 Lightning Bolt\n2 Counterspell\n3 Shock\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        _, new_cur = cmd_find(buffer, cursor, _make_cmd("Counterspell"), ctx)
        assert new_cur.row == 1
        assert "/" in ctx.message

    def test_find_skips_current_line(self) -> None:
        """:find does not match the current line; searches forward."""
        text = "4 Lightning Bolt\n2 Counterspell\n3 Shock\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        _, new_cur = cmd_find(buffer, cursor, _make_cmd("Bolt"), ctx)
        # Only one Bolt line at row 0 — wraps around to row 0
        assert new_cur.row == 0


class TestFindWraps:
    def test_find_wraps_around(self) -> None:
        """:find wraps around from the end of the buffer."""
        text = "4 Lightning Bolt\n2 Counterspell\n3 Shock\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=2)  # On last line
        ctx = EditorContext()

        _, new_cur = cmd_find(buffer, cursor, _make_cmd("Bolt"), ctx)
        assert new_cur.row == 0

    def test_find_wraps_to_earlier_line(self) -> None:
        """:find wraps from middle to an earlier line."""
        text = "4 Lightning Bolt\n2 Counterspell\n3 Shock\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=1)
        ctx = EditorContext()

        _, new_cur = cmd_find(buffer, cursor, _make_cmd("Bolt"), ctx)
        assert new_cur.row == 0


class TestFindNoMatch:
    def test_find_no_match(self) -> None:
        """:find with no match shows informational message."""
        text = "4 Lightning Bolt\n2 Counterspell\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        _, new_cur = cmd_find(buffer, cursor, _make_cmd("Nonexistent"), ctx)
        assert "Pattern not found" in ctx.message
        # Cursor unchanged
        assert new_cur.row == 0

    def test_find_empty_args(self) -> None:
        """:find with no args shows error."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        _, new_cur = cmd_find(buffer, cursor, _make_cmd(""), ctx)
        assert "E: Usage" in ctx.message
        assert ctx.error is True

    def test_find_invalid_regex(self) -> None:
        """:find with invalid regex shows error."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        _, new_cur = cmd_find(buffer, cursor, _make_cmd("[invalid"), ctx)
        assert "E: Invalid pattern" in ctx.message
        assert ctx.error is True


class TestFindCaseInsensitive:
    def test_find_is_case_insensitive(self) -> None:
        """:find matches case-insensitively by default."""
        text = "4 Lightning Bolt\n2 Counterspell\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=1)
        ctx = EditorContext()

        _, new_cur = cmd_find(buffer, cursor, _make_cmd("lightning"), ctx)
        assert new_cur.row == 0

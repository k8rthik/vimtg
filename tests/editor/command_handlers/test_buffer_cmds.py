"""Tests for buffer commands: :w, :q, :wq."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.buffer_cmds import (
    cmd_quit,
    cmd_write,
    cmd_write_quit,
)
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _make_cmd(name: str = "w", bang: bool = False) -> ParsedCommand:
    return ParsedCommand(name=name, bang=bang)


def _sample_buffer() -> Buffer:
    return Buffer.from_text("4 Lightning Bolt\n2 Counterspell\n")


class TestCmdWrite:
    def test_write_sets_message(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(file_path="/tmp/test.deck", modified=True)
        new_buf, new_cur = cmd_write(buf, Cursor(), _make_cmd("w"), ctx)
        assert "Written" in ctx.message
        assert ctx.modified is False
        assert new_buf is buf  # buffer unchanged

    def test_write_no_path_errors(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(file_path=None)
        cmd_write(buf, Cursor(), _make_cmd("w"), ctx)
        assert "No file path" in ctx.message
        assert ctx.error is True


class TestCmdQuit:
    def test_quit_unmodified(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(modified=False)
        cmd_quit(buf, Cursor(), _make_cmd("q"), ctx)
        assert ctx.quit_requested is True

    def test_quit_modified_no_bang(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(modified=True)
        cmd_quit(buf, Cursor(), _make_cmd("q", bang=False), ctx)
        assert ctx.quit_requested is False
        assert "Unsaved changes" in ctx.message
        assert ctx.error is True

    def test_quit_modified_bang(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(modified=True)
        cmd_quit(buf, Cursor(), _make_cmd("q", bang=True), ctx)
        assert ctx.quit_requested is True


class TestCmdWriteQuit:
    def test_write_quit(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(file_path="/tmp/test.deck", modified=True)
        cmd_write_quit(buf, Cursor(), _make_cmd("wq"), ctx)
        assert ctx.quit_requested is True
        assert ctx.modified is False
        assert "Written" in ctx.message

    def test_write_quit_no_path(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(file_path=None, modified=True)
        cmd_write_quit(buf, Cursor(), _make_cmd("wq"), ctx)
        assert ctx.quit_requested is False
        assert ctx.error is True

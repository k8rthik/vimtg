"""Tests for the VCS request command handlers (:history, :commit, :checkpoint)."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.history_cmds import (
    cmd_checkpoint,
    cmd_commit,
    cmd_history,
)
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor

BUF = Buffer.from_text("4 Lightning Bolt\n")


class TestHistory:
    def test_history_sets_open_flag(self) -> None:
        ctx = EditorContext()
        cmd_history(BUF, Cursor(), ParsedCommand(name="history"), ctx)
        assert ctx.open_history_screen is True


class TestCommit:
    def test_commit_sets_description(self) -> None:
        ctx = EditorContext()
        cmd_commit(
            BUF, Cursor(), ParsedCommand(name="commit", args='"new build"'), ctx
        )
        assert ctx.vcs_commit_description == "new build"

    def test_commit_no_description_errors(self) -> None:
        ctx = EditorContext()
        cmd_commit(BUF, Cursor(), ParsedCommand(name="commit"), ctx)
        assert ctx.error is True
        assert "Usage" in ctx.message


class TestCheckpoint:
    def test_checkpoint_sets_request(self) -> None:
        ctx = EditorContext()
        result_buf, _ = cmd_checkpoint(
            BUF, Cursor(), ParsedCommand(name="checkpoint", args="save1"), ctx
        )
        assert ctx.vcs_checkpoint_name == "save1"
        assert result_buf is BUF

    def test_checkpoint_strips_quotes(self) -> None:
        ctx = EditorContext()
        cmd_checkpoint(
            BUF, Cursor(),
            ParsedCommand(name="checkpoint", args='"before refactor"'), ctx,
        )
        assert ctx.vcs_checkpoint_name == "before refactor"

    def test_checkpoint_no_name_errors(self) -> None:
        ctx = EditorContext()
        cmd_checkpoint(BUF, Cursor(), ParsedCommand(name="checkpoint", args=""), ctx)
        assert ctx.error is True
        assert "Usage" in ctx.message
        assert ctx.vcs_checkpoint_name == ""


"""Tests for :checkpoint and :branch command handlers."""

from __future__ import annotations

from unittest.mock import MagicMock

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.history_cmds import cmd_branch, cmd_checkpoint
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _make_ctx(history: object | None = None) -> EditorContext:
    return EditorContext(history=history)


class TestCheckpoint:
    def test_checkpoint_with_name(self) -> None:
        buffer = Buffer.from_text("4 Lightning Bolt\n")
        cursor = Cursor(row=0)
        history = MagicMock()
        ctx = _make_ctx(history=history)
        cmd = ParsedCommand(name="checkpoint", args="save1")

        result_buf, _ = cmd_checkpoint(buffer, cursor, cmd, ctx)
        history.checkpoint.assert_called_once_with("save1")
        assert "Checkpoint: save1" in ctx.message
        assert result_buf is buffer

    def test_checkpoint_strips_quotes(self) -> None:
        buffer = Buffer.from_text("4 Lightning Bolt\n")
        cursor = Cursor(row=0)
        history = MagicMock()
        ctx = _make_ctx(history=history)
        cmd = ParsedCommand(name="checkpoint", args='"before refactor"')

        cmd_checkpoint(buffer, cursor, cmd, ctx)
        history.checkpoint.assert_called_once_with("before refactor")

    def test_checkpoint_no_name_errors(self) -> None:
        buffer = Buffer.from_text("4 Lightning Bolt\n")
        cursor = Cursor(row=0)
        ctx = _make_ctx(history=MagicMock())
        cmd = ParsedCommand(name="checkpoint", args="")

        cmd_checkpoint(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "Usage" in ctx.message

    def test_checkpoint_no_history_errors(self) -> None:
        buffer = Buffer.from_text("4 Lightning Bolt\n")
        cursor = Cursor(row=0)
        ctx = _make_ctx(history=None)
        cmd = ParsedCommand(name="checkpoint", args="save1")

        cmd_checkpoint(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "History not available" in ctx.message


class TestBranch:
    def test_list_branches(self) -> None:
        buffer = Buffer.from_text("4 Lightning Bolt\n")
        cursor = Cursor(row=0)
        history = MagicMock()
        history.list_branches.return_value = ["main", "experiment"]
        ctx = _make_ctx(history=history)
        cmd = ParsedCommand(name="branch", args="")

        cmd_branch(buffer, cursor, cmd, ctx)
        assert "main" in ctx.message
        assert "experiment" in ctx.message

    def test_list_branches_empty(self) -> None:
        buffer = Buffer.from_text("4 Lightning Bolt\n")
        cursor = Cursor(row=0)
        history = MagicMock()
        history.list_branches.return_value = []
        ctx = _make_ctx(history=history)
        cmd = ParsedCommand(name="branch", args="")

        cmd_branch(buffer, cursor, cmd, ctx)
        assert "(none)" in ctx.message

    def test_create_branch(self) -> None:
        buffer = Buffer.from_text("4 Lightning Bolt\n")
        cursor = Cursor(row=0)
        history = MagicMock()
        ctx = _make_ctx(history=history)
        cmd = ParsedCommand(name="branch", args="experiment")

        cmd_branch(buffer, cursor, cmd, ctx)
        history.create_branch.assert_called_once_with("experiment")
        assert "Branch created: experiment" in ctx.message

    def test_switch_branch(self) -> None:
        original_buf = Buffer.from_text("4 Lightning Bolt\n")
        restored_buf = Buffer.from_text("2 Counterspell\n")
        cursor = Cursor(row=0)
        history = MagicMock()
        history.switch_branch.return_value = restored_buf
        ctx = _make_ctx(history=history)
        cmd = ParsedCommand(name="branch", args="experiment", bang=True)

        result_buf, _ = cmd_branch(original_buf, cursor, cmd, ctx)
        history.switch_branch.assert_called_once_with("experiment")
        assert result_buf is restored_buf
        assert "Switched to branch: experiment" in ctx.message
        assert ctx.modified is True

    def test_switch_branch_not_found(self) -> None:
        buffer = Buffer.from_text("4 Lightning Bolt\n")
        cursor = Cursor(row=0)
        history = MagicMock()
        history.switch_branch.return_value = None
        ctx = _make_ctx(history=history)
        cmd = ParsedCommand(name="branch", args="nonexistent", bang=True)

        result_buf, _ = cmd_branch(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "Branch not found" in ctx.message
        assert result_buf is buffer

    def test_branch_no_history_errors(self) -> None:
        buffer = Buffer.from_text("4 Lightning Bolt\n")
        cursor = Cursor(row=0)
        ctx = _make_ctx(history=None)
        cmd = ParsedCommand(name="branch", args="")

        cmd_branch(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "History not available" in ctx.message

"""Tests for the :sync command handler."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry, EditorContext, parse_command
from vimtg.editor.cursor import Cursor


def _run(text: str) -> EditorContext:
    registry = CommandRegistry()
    register_all_commands(registry)
    ctx = EditorContext()
    buffer = Buffer.from_text("4 Lightning Bolt\n")
    registry.execute(parse_command(text, 0, 1), buffer, Cursor(), ctx)
    return ctx


def test_sync_requests_background_sync() -> None:
    ctx = _run("sync")
    assert ctx.card_sync == "sync"
    assert not ctx.error


def test_sync_bang_forces() -> None:
    assert _run("sync!").card_sync == "force"


def test_sync_rejects_arguments() -> None:
    registry = CommandRegistry()
    register_all_commands(registry)
    ctx = EditorContext()
    buffer = Buffer.from_text("")
    out, _ = registry.execute(parse_command("sync now", 0, 1), buffer, Cursor(), ctx)
    assert ctx.error
    assert ctx.message == "E488: Trailing characters: now"
    assert ctx.card_sync == ""
    assert out is buffer


def test_sync_reaches_handler_result() -> None:
    from vimtg.config.settings import Settings
    from vimtg.editor.keymap import ParsedAction
    from vimtg.editor.modes import ModeManager
    from vimtg.editor.registers import RegisterStore
    from vimtg.editor.session import EditorState, handle_command
    from vimtg.services.history_service import HistoryService

    registry = CommandRegistry()
    register_all_commands(registry)
    buffer = Buffer.from_text("4 Lightning Bolt\n")
    state = EditorState(
        buffer=buffer, cursor=Cursor(), mode_mgr=ModeManager(),
        registers=RegisterStore(), history=HistoryService(), modified=False,
        resolved_cards={}, settings=Settings(),
    )
    state.history.initialize(buffer)
    hr = handle_command(
        state, ParsedAction("command_submit", "enter", text="sync!"), registry, None
    )
    assert hr.card_sync == "force"

"""Tests for help text and help command handler."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.help_cmd import cmd_help, register_help_commands
from vimtg.editor.commands import CommandRegistry, EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor
from vimtg.editor.help_text import get_help

# --- get_help unit tests ---


def test_overview_returns_nonempty() -> None:
    text = get_help()
    assert len(text) > 100
    assert "NAVIGATION" in text
    assert "EDITING" in text
    assert "COMMANDS" in text


def test_command_help_sort() -> None:
    text = get_help("sort")
    assert "sort" in text.lower()
    assert "field" in text.lower()


def test_command_help_write() -> None:
    text = get_help("w")
    assert "Save" in text


def test_command_help_substitute() -> None:
    text = get_help("s")
    assert "Substitute" in text


def test_unknown_command_help() -> None:
    text = get_help("nonexistent")
    assert text == "No help for: nonexistent"


# --- cmd_help handler tests ---


def test_cmd_help_sets_overview_message() -> None:
    buf = Buffer.from_text("4 Lightning Bolt\n")
    cursor = Cursor(row=0, col=0)
    ctx = EditorContext()
    cmd = ParsedCommand(name="help", args="")

    result_buf, result_cursor = cmd_help(buf, cursor, cmd, ctx)

    assert "NAVIGATION" in ctx.message
    assert result_buf is buf
    assert result_cursor is cursor


def test_cmd_help_with_topic() -> None:
    buf = Buffer.from_text("4 Lightning Bolt\n")
    cursor = Cursor(row=0, col=0)
    ctx = EditorContext()
    cmd = ParsedCommand(name="help", args="sort")

    cmd_help(buf, cursor, cmd, ctx)

    assert "sort" in ctx.message.lower()


# --- registration ---


def test_register_help_commands() -> None:
    registry = CommandRegistry()
    register_help_commands(registry)
    assert "help" in registry.get_completions("hel")
    assert "h" in registry.get_completions("h")

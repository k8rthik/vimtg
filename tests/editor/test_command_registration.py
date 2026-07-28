"""Every documented command must resolve through the real registration path.

These tests exist because three fully-implemented command modules once
shipped unregistered: their unit tests called the handlers directly and
passed while :s, :g, and / search were dead in the running app.
"""

from __future__ import annotations

import pytest

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    parse_command,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.help_text import COMMAND_HELP


@pytest.fixture
def registry() -> CommandRegistry:
    reg = CommandRegistry()
    register_all_commands(reg)
    return reg


def _execute(registry: CommandRegistry, line: str) -> EditorContext:
    buffer = Buffer.from_text("// Deck\n4 Lightning Bolt\n")
    cursor = Cursor(row=1)
    ctx = EditorContext()
    cmd = parse_command(line, cursor.row, buffer.line_count())
    assert cmd is not None
    registry.execute(cmd, buffer, cursor, ctx)
    return ctx


def test_register_all_has_no_duplicate_names() -> None:
    registry = CommandRegistry()
    register_all_commands(registry)  # raises ValueError on any collision


def test_every_documented_command_is_registered(registry: CommandRegistry) -> None:
    missing = [
        name
        for name in COMMAND_HELP
        if name not in registry._commands and name not in registry._aliases
    ]
    assert missing == []


@pytest.mark.parametrize("line", ["s/Bolt/Shock/", "g/Bolt/d", "find Bolt", "f Bolt"])
def test_search_and_substitute_commands_resolve(
    registry: CommandRegistry, line: str
) -> None:
    ctx = _execute(registry, line)
    assert not (ctx.message or "").startswith("Unknown command")


def test_duplicate_registration_raises() -> None:
    registry = CommandRegistry()

    def handler(buffer, cursor, cmd, ctx):  # type: ignore[no-untyped-def]
        return buffer, cursor

    registry.register("dup", handler)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("dup", handler)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("other", handler, aliases=["dup"])

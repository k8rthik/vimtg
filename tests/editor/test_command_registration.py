"""Every documented command must resolve through the real registration path.

These tests exist because three fully-implemented command modules once
shipped unregistered: their unit tests called the handlers directly and
passed while :s, :g, and / search were dead in the running app.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.config.settings import Settings
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import export_cmds, register_all_commands
from vimtg.editor.commands import (
    CommandRegistry,
    EditorContext,
    parse_command,
)
from vimtg.editor.cursor import Cursor
from vimtg.editor.help_text import COMMAND_HELP
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.keymaps import KeyRemapper
from vimtg.editor.marks import MarkStore
from vimtg.editor.modes import ModeManager
from vimtg.editor.registers import RegisterStore
from vimtg.editor.session import EditorState, HandlerResult, handle_command
from vimtg.services.history_service import HistoryService


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


@pytest.mark.parametrize("line", ["s/Bolt/Shock/", "g/Bolt/d", "g/Bolt/y"])
def test_search_and_substitute_commands_resolve(
    registry: CommandRegistry, line: str
) -> None:
    ctx = _execute(registry, line)
    assert not (ctx.message or "").startswith("E492")


def test_duplicate_registration_raises() -> None:
    registry = CommandRegistry()

    def handler(buffer, cursor, cmd, ctx):  # type: ignore[no-untyped-def]
        return buffer, cursor

    registry.register("dup", handler)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("dup", handler)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("other", handler, aliases=["dup"])


def test_every_command_in_docs_is_registered(registry: CommandRegistry) -> None:
    """docs/commands.md once documented a command that was unregistered."""
    import re
    from pathlib import Path

    doc = (Path(__file__).parents[2] / "docs" / "commands.md").read_text(encoding="utf-8")
    names = {
        m.group(1)
        for m in re.finditer(r"^\| `:(?:\[range\])?([a-z]+)", doc, re.MULTILINE)
    }
    assert "sort" in names
    missing = sorted(
        n for n in names if n not in registry._commands and n not in registry._aliases
    )
    assert missing == []


_ALL = CommandRegistry()
register_all_commands(_ALL)
_COMMANDS = sorted({_ALL.resolve(n) for n in _ALL.get_completions("")})
_ARGLESS = [n for n in _COMMANDS if not _ALL.takes_args(n)]
_TAKES_ARGS = [n for n in _COMMANDS if _ALL.takes_args(n)]
_PROBE_DECK = "// Deck: Probe\n4 Lightning Bolt\n"


def _session() -> EditorState:
    """A session with something in every store a command reads: a
    register, a mark, settings and a key remapper."""
    buffer = Buffer.from_text(_PROBE_DECK)
    state = EditorState(
        buffer=buffer,
        cursor=Cursor(row=1),
        mode_mgr=ModeManager(),
        registers=RegisterStore().set("a", ("4 Lightning Bolt",)),
        history=HistoryService(),
        modified=False,
        resolved_cards={},
        settings=Settings(),
        remapper=KeyRemapper(),
        marks=MarkStore().set("a", 1),
    )
    state.history.initialize(buffer)
    return state


def _outcome(
    registry: CommandRegistry, line: str
) -> tuple[HandlerResult, str, bool, dict[str, str]]:
    """What `:line` did in a fresh session: the result the TUI acts on,
    the deck text, its modified flag and the files written."""
    state = _session()
    written: dict[str, str] = {}
    hr = handle_command(
        state,
        ParsedAction("command_submit", ":", text=line),
        registry,
        None,
        lambda path, text: written.__setitem__(path.name, text),
    )
    return hr, state.buffer.to_text(), state.modified, written


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(export_cmds, "read_clipboard", lambda: None)


def test_some_commands_take_no_argument() -> None:
    assert {"q", "close", "sync", "combos"} <= set(_ARGLESS)


@pytest.mark.usefixtures("sandbox")
@pytest.mark.parametrize("name", _ARGLESS)
def test_command_that_takes_no_argument_refuses_one_with_e488(
    registry: CommandRegistry, name: str
) -> None:
    """vim's `:q junk` is E488 and runs nothing; every command
    registered with takes_args=False refuses the same way."""
    hr, text, modified, written = _outcome(registry, f"{name} junk")
    assert hr == HandlerResult(command_message="E488: Trailing characters: junk", error=True)
    assert (text, modified, written) == (_PROBE_DECK, False, {})


@pytest.mark.usefixtures("sandbox")
@pytest.mark.parametrize("name", _TAKES_ARGS)
def test_command_that_takes_an_argument_does_not_ignore_one(
    registry: CommandRegistry, name: str
) -> None:
    """A command registered without takes_args=False must notice an
    argument: `:cmd junk` acts differently from `:cmd`, or is refused.
    One that ran the same either way ignores it (:q junk quit) and
    belongs with takes_args=False."""
    bare = _outcome(registry, name)
    with_junk = _outcome(registry, f"{name} junk")
    assert with_junk != bare or with_junk[0].error, (
        f":{name} junk did what :{name} does; register it with takes_args=False"
    )

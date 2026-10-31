"""The greeter's `:` command line.

It runs the editor's own handlers for a few commands (GREETER_COMMANDS),
so parsing, aliases and messages (E32, E492, "No help for") are the
editor's; the greeter acts on what the handler asked for. The line's
state is an immutable CommandLineState that each key replaces.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from rich.text import Text

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_completer import CommandCompleter, CompletionState
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry, EditorContext, parse_command
from vimtg.editor.cursor import Cursor
from vimtg.tui.theme import COLORS

# The editor commands the greeter's `:` line runs (with their aliases)
GREETER_COMMANDS = ("edit", "enew", "q", "sync", "help", "tutor")


def greeter_registry() -> CommandRegistry:
    """The editor's own handlers for GREETER_COMMANDS."""
    full = CommandRegistry()
    register_all_commands(full)
    return full.subset(GREETER_COMMANDS)


@dataclass(frozen=True)
class CommandLineState:
    """The open `:` line: its text and any Tab-completion cycle."""

    text: str = ""
    completion: CompletionState | None = None


@dataclass(frozen=True)
class KeyOutcome:
    """What a key did: the line after it (None when it closed) and, on
    Enter, the text to run."""

    line: CommandLineState | None
    submitted: str | None = None


def feed(
    line: CommandLineState, key: str, char: str | None, completer: CommandCompleter,
) -> KeyOutcome:
    """Esc (or Backspace on an empty line) closes, Enter submits, Tab /
    Shift-Tab complete; anything printable is typed."""
    text = line.text
    if key == "escape" or (key == "backspace" and not text):
        return KeyOutcome(None)
    if key == "enter":
        return KeyOutcome(None, text.strip())
    if key in ("tab", "shift_tab"):
        return KeyOutcome(_complete(line, completer, backward=key == "shift_tab"))
    if key == "backspace":
        return KeyOutcome(CommandLineState(text[:-1]))
    if char and len(char) == 1 and char.isprintable():
        return KeyOutcome(CommandLineState(text + char))
    return KeyOutcome(line)


def _complete(
    line: CommandLineState, completer: CommandCompleter, *, backward: bool,
) -> CommandLineState:
    state = line.completion
    if state is None or not state.matches:
        state = completer.complete(line.text)
    elif backward:
        state = CommandCompleter.cycle_prev(state)
    else:
        state = CommandCompleter.cycle_next(state)
    return replace(line, text=CommandCompleter.accept(state) or line.text, completion=state)


def run(text: str, registry: CommandRegistry) -> EditorContext:
    """Run `text` through the handlers; the context says what they asked for."""
    ctx = EditorContext()
    registry.execute(parse_command(text, 0, 0), Buffer.from_text(""), Cursor(), ctx)
    return ctx


def render(line: CommandLineState) -> Text:
    """`:text` with a block cursor."""
    t = Text("  :", style=f"bold {COLORS['fg']}")
    t.append(line.text, style="bold")
    t.append(" ", style="reverse")
    t.append("\n")
    return t

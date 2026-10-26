"""Every primitive the editor offers, each owned by exactly one slice.

Ids:
  normal-mode key      as the keyspec spells it: "dd", "zs", "m{a-z}"
  other keyspec modes  "<mode>:<key>": "visual:d", "cmdline:up"
  operator + target    "<op> <motion>": "d w", "y }", "c ctrl_d"
  insert (card search) "insert:<action>": "insert:tab"
  ex command           ":<canonical name>": ":w", ":sort"

The keys and ex commands come from the live keyspec and command registry,
so a new binding or command shows up here, and in the gate, by itself.
"""

from __future__ import annotations

from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry
from vimtg.editor.keyspec import EDITOR_BINDINGS
from vimtg.editor.operators import EXCLUSIVE_MOTIONS, LINEWISE_MOTIONS

OPERATORS = ("d", "y", "c")
INSERT_ACTIONS = ("type", "backspace", "tab", "shift_tab", "enter", "escape")

SLICES = (
    "navigation",
    "editing",
    "operators",
    "visual",
    "structure",
    "input",
    "files_and_panes",
)

# Default slice per keyspec group; OVERRIDES moves single ids.
_GROUP_SLICE = {
    "MODES": "input",
    "NAVIGATION": "navigation",
    "EDITING": "editing",
    "ZONES": "structure",
    "MARKS, MACROS & REGISTERS": "editing",
    "VISUAL MODE": "visual",
    "CATEGORIES": "structure",
    "WINDOWS, PANES & THE LEADER": "files_and_panes",
    "VERSION CONTROL": "files_and_panes",
    "COMMAND LINE": "input",
}

_OVERRIDES = {
    "m{a-z}": "navigation",
    "'{a-z}": "navigation",
    "v": "visual",
    "V": "visual",
    "gv": "visual",
    "[v": "structure",
    "]v": "structure",
    "space f": "structure",
    "n": "input",
    "N": "input",
    "*": "input",
    "#": "input",
    "K": "input",
    "f1": "files_and_panes",
    "g?": "files_and_panes",
    "ZZ": "files_and_panes",
    "ZQ": "files_and_panes",
}

_EX_SLICE = {
    "category": "structure", "categories": "structure", "layout": "structure",
    "filter": "structure", "plan": "structure", "plans": "structure",
    "dtag": "structure", "duntag": "structure", "sort": "structure",
    "s": "input", "g": "input", "v": "input", "map": "input", "unmap": "input",
    "set": "input", "marks": "navigation", "registers": "editing",
    "messages": "input",
}


def _key_id(mode: str, key: str) -> str:
    return key if mode == "normal" else f"{mode}:{key}"


def ex_commands() -> tuple[str, ...]:
    registry = CommandRegistry()
    register_all_commands(registry)
    return tuple(sorted(registry._commands))


def inventory() -> dict[str, str]:
    """Primitive id -> owning slice."""
    owned: dict[str, str] = {}
    for binding in EDITOR_BINDINGS:
        for key in binding.keys:
            pid = _key_id(binding.mode, key)
            owned[pid] = _OVERRIDES.get(pid, _GROUP_SLICE[binding.group])
    for op in OPERATORS:
        for motion in sorted(EXCLUSIVE_MOTIONS | LINEWISE_MOTIONS):
            owned[f"{op} {motion}"] = "operators"
    for action in INSERT_ACTIONS:
        owned[f"insert:{action}"] = "input"
    for name in ex_commands():
        owned[f":{name}"] = _EX_SLICE.get(name, "files_and_panes")
    return owned

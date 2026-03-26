"""Help text for the vimtg editor — overview and per-command help strings."""

from __future__ import annotations

HELP_OVERVIEW = """
NAVIGATION
  j/k           Move down/up
  gg/G          First/last line
  w/b           Next/prev card entry
  {/}           Next/prev section
  Ctrl-D/U      Half page down/up

EDITING
  i             Edit current line as plain text
  o/O           Add card (new line below / above)
  dd            Delete card line
  yy            Yank (copy) card line
  p/P           Paste below/above
  +/-           Increment/decrement quantity
  .             Repeat last change
  u / Ctrl-R    Undo / redo

VISUAL MODE
  v/V           Enter visual / visual-line
  d/y           Delete/yank selection
  Escape        Exit visual

COMMANDS
  :w            Save deck
  :q            Quit (:q! force)
  :wq           Save and quit
  :sort [field] Sort by name/cmc/type/qty
  :s/old/new/g  Substitute across deck
  :g/pat/d      Delete matching cards
  :find pattern Jump to matching card
  :export fmt   Export (arena/mtgo/moxfield)
  :help         This help
""".strip()

COMMAND_HELP: dict[str, str] = {
    "w": ":w [file]  Save deck to file",
    "q": ":q        Quit (:q! force quit with unsaved changes)",
    "wq": ":wq      Save and quit",
    "sort": (
        ":sort [field]  Sort cards in current section\n"
        "\n"
        "Fields: name (default), qty\n"
        ":sort!  reverse order\n"
        ":5,10sort  sort specific range"
    ),
    "s": (
        ":s/old/new/[flags]  Substitute text\n"
        "\n"
        ":%s/old/new/g  whole file\n"
        "Flags: g (all occurrences), i (case-insensitive)"
    ),
    "g": (
        ":g/pattern/cmd  Execute command on matching lines\n"
        "\n"
        ":g/Bolt/d      delete lines matching 'Bolt'\n"
        ":v/SB:/d       delete non-sideboard lines"
    ),
    "find": ":find pattern  Jump to next card matching pattern",
    "export": ":export format [file]  Export deck (arena/mtgo/moxfield/archidekt)",
    "help": ":help [command]  Show help",
}


def get_help(command: str | None = None) -> str:
    """Return help text for a specific command, or the full overview."""
    if command is None:
        return HELP_OVERVIEW
    return COMMAND_HELP.get(command, f"No help for: {command}")

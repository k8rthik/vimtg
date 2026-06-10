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

TAGS
  ta            Add tag to current card
  tr            Remove tag
  tt            Toggle tag
  tf            Filter view by tag expression
  tl            List tags with counts
  tc            Clear tags from current card
  tn / tp       Next / prev card sharing a tag

COMMANDS
  :w            Save deck
  :q            Quit (:q! force)
  :wq           Save and quit
  :sort [field] Sort by name/cmc/type/qty
  :s/old/new/g  Substitute across deck
  :g/pat/d      Delete matching cards
  :find pattern Jump to matching card
  :tag name     Add tag (range supported)
  :untag name   Remove tag (:untag! clears all)
  :tags         List tags with counts
  :filter expr  Filter view by tag (+ AND, | OR, - NOT)
  :retag /a/b/  Rename tag across deck
  :export fmt   Export (arena/mtgo/moxfield/archidekt)
  :import file  Import deck (auto-detects format)
  :clipboard    Copy deck to system clipboard (default arena)
  :help         This help

VERSION CONTROL
  :history      Open deck history (lazygit-style)
  :commit "msg" Snapshot current deck state
  :branch       List branches; :branch name creates; :branch! switches
  :checkpoint n Tag current undo-tree state
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
    "import": ":import file  Import deck (auto-detects format, replaces buffer)",
    "clipboard": (
        ":clipboard [format]  Copy deck to system clipboard via OSC52\n"
        "\n"
        "Default format is arena. Use mtgo/moxfield/archidekt/vimtg for others.\n"
        "Best-effort: terminal must support OSC52 (iTerm2, kitty, Alacritty,\n"
        "Wezterm, Windows Terminal)."
    ),
    "tag": (
        ":tag name  Add tag to cards in range (default: current line)\n"
        "\n"
        ":tag flex          tag current card #flex\n"
        ":5,10tag budget    tag lines 5-10 #budget\n"
        ":%tag staple       tag every card #staple"
    ),
    "untag": (
        ":untag name  Remove tag (use :untag! to clear all tags)\n"
        "\n"
        ":untag flex        remove #flex from current card\n"
        ":%untag!           clear all tags from every card"
    ),
    "tags": ":tags  List tags with counts",
    "filter": (
        ":filter expr  Show only cards matching tag expression\n"
        "\n"
        ":filter core              cards tagged #core\n"
        ":filter core+staple       AND (both tags)\n"
        ":filter flex|budget       OR (either tag)\n"
        ":filter core-removal      AND NOT\n"
        ":filter                   clear filter"
    ),
    "retag": ":retag /old/new/  Rename a tag across the entire deck",
    "help": ":help [command]  Show help",
    "history": (
        ":history  Open lazygit-style deck version control\n"
        "\n"
        "Keybindings in history screen:\n"
        "  Tab/Shift-Tab  Cycle panels\n"
        "  j/k            Navigate\n"
        "  c              Commit snapshot\n"
        "  b              Create branch\n"
        "  B              Switch branch\n"
        "  t/T            Tag/untag snapshot\n"
        "  R              Restore snapshot\n"
        "  p              Cherry-pick\n"
        "  d              Toggle detail view\n"
        "  q              Return to editor"
    ),
    "commit": ":commit message  Create a named snapshot of current deck state",
    "branch": ":branch  Open history screen for branch management",
    "checkpoint": ":checkpoint name  Alias for :commit",
}


def has_help(command: str) -> bool:
    """Return True if per-command help exists for the given command."""
    return command in COMMAND_HELP


def get_help(command: str | None = None) -> str:
    """Return help text for a specific command, or the full overview."""
    if command is None:
        return HELP_OVERVIEW
    return COMMAND_HELP.get(command, f"No help for: {command}")

"""Help text for the vimtg editor — overview and per-command help strings."""

from __future__ import annotations

HELP_OVERVIEW = """
COUNTS
  {n}key        Repeat/scale any motion or edit: 5j down 5 lines,
                3dd delete 3 cards, 10+ add 10 to quantity,
                2x delete 2 cards, 3p paste 3 copies, 3@a play macro 3x

NAVIGATION
  j/k           Move down/up
  gg/G          First/last line
  w/b           Next/prev card entry
  {/}           Prev/next section
  [[/]]         Prev/next section header
  Ctrl-D/U      Half page down/up
  m{a-z}        Set mark (s/m/d are taken by zone moves)
  '{a-z}        Jump to mark

EDITING
  i             Edit current line as plain text
                (on // Key: metadata lines, edits just the value)
  A             Add/edit card comment (empty removes)
  o/O           Add card (new line below / above)
  dd            Delete card line
  x             Delete card line (into register)
  yy            Yank (copy) card line
  p/P           Paste below/above
  "{a-z}        Use named register for yank/paste
  +/-           Increment/decrement quantity
  ms/mm/md      Move card to sideboard/maybeboard/main deck
                (all copies; 2ms moves just 2)
  .             Repeat last change
  u / Ctrl-R    Undo / redo
  q{a-z} / q    Record macro / stop recording
  @{a-z} / @@   Play macro / replay last

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
  :wq / :x      Save and quit
  :home         Return to greeter (:home! discards changes)
  :sort [field] Sort by name/qty/cmc/type/color/tag
  :s/old/new/g  Substitute across deck
  :g/pat/d      Delete matching cards
  :find pattern Jump to matching card
  :stats        Deck statistics
  :validate     Check format legality (uses // Format:)
  :tag name     Add tag (range supported)
  :untag name   Remove tag (:untag! clears all)
  :tags         List tags with counts
  :dtag/:duntag Add/remove deck-level tags
  :filter expr  Filter view by tag (+ AND, | OR, - NOT)
  :retag /a/b/  Rename tag across deck
  :export fmt   Export (arena/mtgo/moxfield/archidekt/vimtg)
  :import file  Import deck (auto-detects format)
  :clipboard    Copy deck to system clipboard (default arena)
  :set opt=val  Change a setting (:set shows all)
  :config       Open the settings screen
  :map / :unmap Key remapping for this session
  :help         This help

VERSION CONTROL
  :history      Open deck history (lazygit-style)
  :commit "msg" Snapshot current deck state
  :branch       Undo-tree branches: list; name creates; ! switches
  :checkpoint n Tag current undo-tree state
""".strip()

COMMAND_HELP: dict[str, str] = {
    "w": ":w [file]  Save deck to file",
    "q": ":q        Quit (:q! force quit with unsaved changes)",
    "wq": ":wq      Save and quit",
    "sort": (
        ":sort [field]  Sort cards in current section\n"
        "\n"
        "Fields: name (default), qty, cmc, type, color, tag\n"
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
    "export": (
        ":export format [file]  Export deck "
        "(arena/mtgo/moxfield/archidekt/vimtg)"
    ),
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
        ":filter expr  Highlight cards matching a tag expression\n"
        "(non-matching cards are dimmed)\n"
        "\n"
        ":filter core              cards tagged #core\n"
        ":filter core+staple       AND (both tags)\n"
        ":filter flex|budget       OR (either tag)\n"
        ":filter core-removal      AND NOT\n"
        ":filter / :filter!        clear filter"
    ),
    "retag": ":retag /old/new/  Rename a tag across the entire deck",
    "help": ":help [command]  Open full-screen help (also F1; q closes)",
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
    "branch": (
        ":branch  Undo-tree branches (in-memory, this session)\n"
        "\n"
        ":branch          list branches\n"
        ":branch name     create branch at current state\n"
        ":branch! name    switch to branch\n"
        "\n"
        "For saved snapshots and persistent branches, use :history."
    ),
    "checkpoint": (
        ":checkpoint name  Tag the current undo-tree state\n"
        "\n"
        "Checkpoints live in this session's undo tree. For a persistent\n"
        "snapshot use :commit."
    ),
    "stats": ":stats  Show deck statistics (mana curve, colors, types)",
    "validate": (
        ":validate  Check deck legality for its format\n"
        "\n"
        "Uses the deck's // Format: line (falling back to the\n"
        "default_format setting): banned/restricted/not-legal cards,\n"
        "deck size, copy limits, commander rules. Without a format,\n"
        "checks generic 60-card rules. Issues also show live as\n"
        "gutter signs (✗ error, ! warning)."
    ),
    "set": (
        ":set option=value  View or change settings\n"
        "\n"
        ":set                 show all settings\n"
        ":set number          enable (bool shorthand)\n"
        ":set nonumber        disable\n"
        ":set price_source=eur"
    ),
    "config": ":config  Open the settings screen (j/k navigate, s save)",
    "map": (
        ":map key action  Remap a NORMAL-mode key for this session\n"
        "\n"
        ":map s :w        's' saves\n"
        ":map              list mappings\n"
        "Persist mappings in ~/.config/vimtg/config.toml [keybindings]."
    ),
    "unmap": ":unmap key  Remove a key remapping",
    "home": ":home  Return to the greeter (:home! discards changes)",
}


def is_section_header(line: str) -> bool:
    """True for HELP_OVERVIEW section headers (shared by all renderers)."""
    return bool(line) and not line.startswith(" ")


def has_help(command: str) -> bool:
    """Return True if per-command help exists for the given command."""
    return command in COMMAND_HELP


def get_help(command: str | None = None) -> str:
    """Return help text for a specific command, or the full overview."""
    if command is None:
        return HELP_OVERVIEW
    return COMMAND_HELP.get(command, f"No help for: {command}")

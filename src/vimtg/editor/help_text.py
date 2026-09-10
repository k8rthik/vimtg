"""Help text for the vimtg editor — overview and per-command help strings."""

from __future__ import annotations

from vimtg.editor.keyspec import format_overview_group, overview_groups

_COUNTS = """
COUNTS
  {n}key        Repeat/scale any motion or edit: 5j down 5 lines,
                3dd delete 3 cards, 10+ add 10 to quantity,
                2x delete 2 cards, 3p paste 3 copies, 3@a play macro 3x
""".strip()

_COMMANDS = """
COMMANDS
  :w            Save deck
  :q            Quit (:q! force)
  :wq / :x      Save and quit
  :home         Return to greeter (:home! discards changes)
  :sort [field] Sort by cmc/name/qty/type/color/tag/category/
                power/toughness/rarity/price (default: sort_order)
  :s/old/new/g  Substitute across deck
  :g/pat/d      Delete matching cards
  :find pattern Jump to matching card
  :stats        Deck statistics
  :validate     Check format legality (uses // Format:)
  :cat name     Set card category (:cat! clears)
  :categories   List categories with counts
  :layout       Toggle type/category layout
  :tag name     Add tag (range supported)
  :untag name   Remove tag (:untag! clears all)
  :tags         List tags with counts
  :dtag/:duntag Add/remove deck-level tags
  :filter expr  Filter view by tag (+ AND, | OR, - NOT)
  :retag /a/b/  Rename tag across deck
  :export fmt   Export (arena/mtgo/dek/moxfield/archidekt/vimtg/guide)
  :plan name    Activate a sideboard plan (creates its VS: block)
  :plans        List the plans with their -out +in totals
  :import src   Import deck from a file (auto-detects format) or a
                deck URL (Moxfield, Archidekt, ManaBox, Deckstats,
                TappedOut, MTGGoldfish)
  :clipboard    Copy deck to system clipboard (default arena)
  :set opt=val  Change a setting (:set shows all)
  :config       Open the settings screen
  :map / :unmap Key remapping for this session
  :help         This help
""".strip()

_VCS_COMMANDS = """
VERSION CONTROL
  :history      Same, as a command
  :commit "msg" Snapshot current deck state
  :branch       Branches: list; name creates; ! switches
  :checkpoint n Commit and tag the current state
  :merge x      Merge branch x (or another .deck file)
  :rebase x     Replay this branch's commits onto branch x
""".strip()


def _build_overview() -> str:
    """The keybinding sections come from the key spec; the ex-command
    sections are prose kept here."""
    parts = [_COUNTS]
    for title, rows in overview_groups():
        if title == "VERSION CONTROL":
            parts.append(format_overview_group(title, rows) + "\n" + "\n".join(
                _VCS_COMMANDS.split("\n")[1:]
            ))
        else:
            parts.append(format_overview_group(title, rows))
    # COMMANDS sits between TAGS and VERSION CONTROL, as before
    vcs = parts.pop()
    parts.append(_COMMANDS)
    parts.append(vcs)
    return "\n\n".join(parts)


HELP_OVERVIEW = _build_overview()

COMMAND_HELP: dict[str, str] = {
    "w": ":w [file]  Save deck to file",
    "q": ":q        Quit (:q! force quit with unsaved changes)",
    "wq": ":wq      Save and quit",
    "sort": (
        ":sort [field]  Sort cards in current section\n"
        "\n"
        "Fields: name, qty, cmc, type, color, tag, category,\n"
        "power, toughness, rarity, price\n"
        "Without a field, the sort_order setting decides (default cmc)\n"
        ":sort!  reverse order\n"
        ":5,10sort  sort specific range"
    ),
    "category": (
        ":category name  Set the card's category (alias :cat)\n"
        "\n"
        "A category is one purpose label per card (@ramp, @draw,\n"
        "@wincon) driving the category layout (:layout).\n"
        "\n"
        ":cat ramp          categorize current card @ramp\n"
        ":5,10cat draw      categorize lines 5-10\n"
        ":cat!              clear category\n"
        ":cat               show current card's category\n"
        "\n"
        "Keys: gc set (Tab completes), gC clear."
    ),
    "categories": (
        ":categories  List categories with counts (alias :cats)\n"
        "\n"
        ":categories ramp   list cards in @ramp"
    ),
    "layout": (
        ":layout [type|category]  Regroup the deck's sections\n"
        "\n"
        "type      group under // Creatures, // Instants, ...\n"
        "category  group under // @ramp, // @draw, ... headers\n"
        "No argument toggles (also the gl key). Cards keep their\n"
        "@category token, so toggling is lossless. In-group order\n"
        "follows the sort_order setting."
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
        "(arena/mtgo/dek/moxfield/archidekt/vimtg/guide)\n"
        "\n"
        "guide writes the sideboard plans (VS: blocks) as a Markdown\n"
        "guide — one section per matchup with OUT and IN lines."
    ),
    "plan": (
        ":plan <matchup>  Activate a sideboard plan; :plan cycles; :plan! clears\n"
        "\n"
        "A plan is a 'VS: <matchup>' block at the end of the deck with\n"
        "'-N Card' (out of the mainboard) and '+N Card' (in from the\n"
        "sideboard) lines under it. :plan creates the block when the\n"
        "name is new and moves the cursor to it. With a plan active,\n"
        "zo/zi on a deck card board it out/in (count = copies, bare =\n"
        "all), deck cards show their -N/+N, the status line shows the\n"
        "running totals, and :analytics reports the post-board deck.\n"
        "Inside the block: o adds a card (searching the deck's own\n"
        "cards), +/- adjust a line, dd removes it. ]v/[v jump between\n"
        "plans. Lint flags ins that are not in the sideboard, outs not\n"
        "in the mainboard, over-counts, and unbalanced plans."
    ),
    "plans": ":plans  List every sideboard plan with its -out +in totals",
    "import": (
        ":import <file|url>  Import a deck (replaces buffer, undoable)\n"
        "\n"
        "Files auto-detect their format: vimtg, MTGO text or .dek,\n"
        "Arena (MTGA), Moxfield CSV, Archidekt CSV. A deck URL from\n"
        "Moxfield, Archidekt, ManaBox, Deckstats, TappedOut, or\n"
        "MTGGoldfish fetches the list from the site: commander,\n"
        "companion, sideboard, and maybeboard land in their own zones,\n"
        "Archidekt user categories become @categories, and the URL is\n"
        "remembered as // Source:."
    ),
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
        ":history  Open the lazygit-style history overlay (also gh)\n"
        "\n"
        "A floating window over the editor with five panels:\n"
        "  1 Working copy   uncommitted changes vs the branch tip\n"
        "  2 Branches       3 Snapshots   4 Diff   5 Stats\n"
        "\n"
        "Keybindings in the overlay:\n"
        "  1-5 / Tab      Jump to / cycle panels\n"
        "  j/k / wheel    Navigate or scroll\n"
        "  gg/G  Ctrl-D/U Top/bottom, half page\n"
        "  Enter          Open: switch branch, or jump to Diff\n"
        "  c              Commit snapshot\n"
        "  b              Create branch at the tip\n"
        "  B / D          Switch to / delete branch (Branches panel)\n"
        "  m / r          Merge / rebase onto branch (Branches panel)\n"
        "  t/T            Tag/untag snapshot\n"
        "  R              Restore snapshot\n"
        "  p              Cherry-pick\n"
        "  d              Toggle unchanged cards in the diff\n"
        "  q / Esc / gh   Return to editor\n"
        "  ? / F1         This topic / full help"
    ),
    "commit": ":commit message  Create a named snapshot of current deck state",
    "branch": (
        ":branch  Persistent deck branches (saved across sessions)\n"
        "\n"
        ":branch          list branches (* marks current)\n"
        ":branch name     create branch at current tip\n"
        ":branch! name    switch to branch (loads its tip)\n"
        "\n"
        "Browse branches and snapshots with :history."
    ),
    "checkpoint": (
        ":checkpoint name  Commit the current state and tag it\n"
        "\n"
        "Shorthand for :commit followed by tagging the new snapshot."
    ),
    "merge": (
        ":merge target  Merge into the current branch\n"
        "\n"
        ":merge branch        merge another branch (3-way, fast-forwards\n"
        "                     when possible)\n"
        ":merge path.deck     merge another deck file's cards\n"
        "\n"
        "Conflicting card quantities open an interactive resolution screen."
        "\n"
        "Keys in the conflict screen:\n"
        "  j/k  gg/G  Ctrl-D/U  Move between conflicts (or the wheel)\n"
        "  o / t          Take ours / theirs\n"
        "  c              Custom quantity (0 omits the card)\n"
        "  u              Unresolve\n"
        "  Enter          Confirm (every conflict must be resolved)\n"
        "  q / Esc        Abort — nothing is committed\n"
        "  ? / F1         This topic / full help"
    ),
    "rebase": (
        ":rebase branch  Replay this branch's commits onto another tip\n"
        "\n"
        "Rewrites the current branch as if it had started from the target\n"
        "branch's tip. Overlapping edits resolve in favor of the replayed\n"
        "commit. Original snapshots stay recoverable by id."
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
    "config": (
        ":config  Open the settings screen\n"
        "\n"
        "Keys in the settings screen:\n"
        "  j/k  gg/G  Ctrl-D/U  Navigate (or the mouse wheel)\n"
        "  h / l          Cycle the value back / forward\n"
        "  Space / Enter  Cycle forward\n"
        "  s              Save and close\n"
        "  q / Esc        Close (asks again when there are unsaved changes)\n"
        "  ? / F1         This topic / full help"
    ),
    "map": (
        ":map key action  Remap a NORMAL-mode key for this session\n"
        "\n"
        ":map s :w        's' saves\n"
        ":map              list mappings\n"
        "Persist mappings in ~/.config/vimtg/config.toml [keybindings]."
    ),
    "unmap": ":unmap key  Remove a key remapping",
    "home": ":home  Return to the greeter (:home! discards changes)",
    "vsplit": (
        ":vsplit deck-file  Open another deck beside this one (alias :vsp, :vs)\n"
        "\n"
        "The split pane is read-only — compare a netdeck or an old\n"
        "version while editing. Ss switches pane focus (j/k scroll,\n"
        "Esc returns), Sc / :close closes it."
    ),
    "split": (
        ":split deck-file  Open another deck below this one (alias :sp, :hsplit)\n"
        "\n"
        "Horizontal variant of :vsplit — same keys: Ss switch, :close close."
    ),
    "close": ":close  Close the split pane (alias :only; also the Sc key)",
    "edhrec": (
        ":edhrec [type]  EDHREC recommendations for the commander (alias :rec)\n"
        "\n"
        "Commander decks only: uses the CMD: line(s), partner pairs\n"
        "included. Opens a side pane with one tab per card type;\n"
        "the optional argument jumps to a tab (creature, instant,\n"
        "sorcery, artifact, enchantment, planeswalker, battle, land).\n"
        "\n"
        "In the pane: j/k select, h/l switch tabs, Enter adds the\n"
        "card to the deck, Esc returns to the editor. ✓ marks cards\n"
        "already in the deck. Results are cached for 7 days."
    ),
    "analytics": (
        ":analytics  Live deck-analytics pane (alias :ana; also the Sa key)\n"
        "\n"
        "Mana curve, card counts per type / zone / category, a\n"
        "mana-base check (colored sources vs pip requirements, a\n"
        "Karsten-style heuristic scaled to deck size), and draw\n"
        "odds. The odds line follows the cursor: put it on a card\n"
        "to see the chance of drawing one by the opener or turn 3.\n"
        "Everything recomputes as the deck is edited.\n"
        "\n"
        "Ss focuses the pane (j/k scroll, Esc back); :close closes."
    ),
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

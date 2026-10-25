"""Help text for the vimtg editor — overview and per-command help strings."""

from __future__ import annotations

from vimtg.editor.keyspec import format_overview_group, overview_groups

_GETTING_STARTED = """
GETTING STARTED
  Modes         vimtg is modal, like vim: NORMAL mode moves and edits
                with single keys; o / i open a prompt to type into;
                Esc (or Ctrl-C) always returns to NORMAL
  o             Add a card: type part of its name, Tab/Down picks,
                Enter adds it (+/- change the quantity after)
  :w            Save (a new deck is named after its // Deck: line)
  :q            Quit (:q! quits without saving, :wq saves and quits)
  F1, :help     This full help (g? toggles a cheat sheet)
  q             Careful: q starts recording a macro (the status line
                says "recording @a"); press q again to stop
  :messages     Show recent messages and errors again
  :tips         Show the getting-started tips (:tips off hides them)
  :Tutor        A 15-minute hands-on lesson deck, like vimtutor
""".strip()

_COUNTS = """
COUNTS
  {n}key        Repeat/scale any motion or edit: 5j down 5 lines,
                3dd delete 3 cards, 10+ add 10 to quantity,
                2x delete 2 cards, 3p paste 3 copies, 3@a play macro 3x
""".strip()

_COMMANDS = """
COMMANDS
  :w            Save deck
  :q            Quit (:q! force); with a pane open, close the pane
  :qa / :wqa    Quit / save and quit, pane or not (:xa, :wa write)
  :wq           Save and quit
  :x / ZZ       Save if changed, then quit
  :saveas file  Write to file and edit it from now on
  :home         Return to greeter (:home! discards changes)
  :recover      Load the crash-recovery copy (:recover! discards it)
  :sort [field] Sort by cmc/name/qty/type/color/tag/category/
                power/toughness/rarity/price (default: sort_order)
  :{n}          Go to line n
  :e[!] [file]  Edit another deck (:e! reloads, dropping changes)
  :s/pat/rep/g  Substitute (regex; & and \\1 in rep)
  :g/pat/cmd    Run d, p, y [x], or s/// on matching cards
  :d/:y [x] [n] Delete / yank lines (range, or n lines) into
                register x
  :m {n} :t {n} Move / copy lines below line n
  :undo :redo   One undo / redo step
  :reg :marks   Show registers / marks
  :find pattern Jump to matching card
  :search [q]   Open card search (as o) with query q
  :stats        One-line deck summary (:analytics has more)
  :validate     Check format legality (uses // Format:)
  :hand [seed]  Sample hand / goldfish (draw, mulligan; Space h)
  :cat name     Set card category (:cat! clears)
  :categories   List categories with counts
  :layout       Toggle type/category layout
  :dtag/:duntag Add/remove deck-level tags
  :filter expr  Filter view by category (| OR, - NOT; Space f)
  :export fmt   Export (arena/mtgo/dek/moxfield/archidekt/vimtg/guide)
  :plan name    Activate a sideboard plan (creates its VS: block)
  :plans        List the plans with their -out +in totals
  :import src   Import deck from a file (auto-detects format) or a
                deck URL (Moxfield, Archidekt, ManaBox, Deckstats,
                TappedOut, MTGGoldfish); no argument reads the clipboard
  :clipboard    Copy deck to system clipboard (default arena)
  :sync         Download card data in the background (:sync! forces)
  :set opt=val  Change a setting (:set shows all)
  :config       Open the settings screen
  :map / :unmap Key remapping for this session
  :help         This help
  :messages     Recent messages and errors (:messages clear)
  :tips         Getting-started tips (:tips off / :tips on)
  :Tutor        The vimtg tutor (also `vimtg tutor`)
""".strip()

_VCS_COMMANDS = """
VERSION CONTROL
  :history      Same, as a command
  :commit "msg" Snapshot current deck state
  :checkpoint n Commit and tag the current state
""".strip()


def _build_overview() -> str:
    """The keybinding sections come from the key spec; the ex-command
    sections are prose kept here."""
    parts = [_GETTING_STARTED, _COUNTS]
    for title, rows in overview_groups():
        if title == "VERSION CONTROL":
            parts.append(format_overview_group(title, rows) + "\n" + "\n".join(
                _VCS_COMMANDS.split("\n")[1:]
            ))
        else:
            parts.append(format_overview_group(title, rows))
    # COMMANDS sits between the key groups and VERSION CONTROL
    vcs = parts.pop()
    parts.append(_COMMANDS)
    parts.append(vcs)
    return "\n\n".join(parts)


HELP_OVERVIEW = _build_overview()

COMMAND_HELP: dict[str, str] = {
    "w": (
        ":w [file]  Save deck to file\n"
        "\n"
        ":w file  writes a copy to file and goes on editing this deck, its\n"
        "         changes still unsaved (as vim); a deck with no file yet\n"
        "         takes the name. :saveas file switches to it\n"
        ":w!      overwrite another existing file, or a file changed on disk\n"
        "\n"
        "A deck with no file yet is written to the current directory,\n"
        "named after its // Deck: line (Burn -> burn.deck, burn-2.deck\n"
        "if taken). Empty // Format: or // Tags: lines the file never\n"
        "had are not written."
    ),
    "q": (
        ":q        Quit (:q! force quit with unsaved changes)\n"
        "\n"
        "With a split pane open, :q (and :wq, :x, ZZ, ZQ) close the pane,\n"
        "the other window, as in vim. :qa quits vimtg whatever is open."
    ),
    "wq": ":wq      Save and quit",
    "x": ":x       Save if there are changes, then quit (ZZ)",
    "saveas": ":saveas file  Write to file and edit that file from now on",
    "recover": (
        ":recover  Load the crash-recovery copy of this deck\n"
        "\n"
        "If vimtg hits an internal error, or the session ends with unsaved\n"
        "changes (terminal closed, SSH dropped, Ctrl-Q, a kill),\n"
        "the buffer is saved under ~/.local/state/vimtg/recovery/.\n"
        "Opening that deck again offers the copy; copies of unnamed\n"
        "buffers or deleted files are listed on the greeter (R).\n"
        ":q! and ZQ discard changes and the copy with them.\n"
        "\n"
        ":recover   replace the buffer with the copy (undoable, unsaved)\n"
        ":recover!  delete the copy\n"
        "The copy is removed by the next successful :w"
    ),
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
        ":s/pat/rep/[flags]  Substitute text\n"
        "\n"
        "pat is a regex, case-insensitive like / and :g; an empty pat\n"
        "reuses the last search. In rep, & is the match, \\1-\\9 groups,\n"
        "\\& a literal &.\n"
        ":%s/old/new/g  whole file\n"
        "Flags: g (all occurrences), I (match case), i (ignore case)\n"
        ". repeats the last :s on the cursor line"
    ),
    "g": (
        ":g/pattern/cmd  Execute command on matching card lines\n"
        "(every zone; :v or :g! for non-matching lines)\n"
        "\n"
        ":g/Bolt/d          delete lines matching 'Bolt'\n"
        ":g/Bolt/p          list the matches\n"
        ":g/Bolt/y a        yank them into register a\n"
        ":g/@ramp/s/^4/3/   substitute on each match\n"
        ":v/SB:/d           delete card lines without an SB: prefix"
    ),
    "edit": (
        ":e [file]  Edit another deck in place of this one\n"
        "\n"
        ":e file   open file (deck.deck for 'deck'; a new file is a new deck)\n"
        ":e! file  the same, discarding unsaved changes\n"
        ":e!       reload this deck from disk\n"
        "Registers carry over."
    ),
    "enew": (
        ":enew  Edit a new, unnamed deck in place of this one (also :ene)\n"
        "\n"
        "The new-deck wizard asks for its name and format, as the\n"
        "greeter's n does; the first :w names the file after // Deck:.\n"
        "Refuses with unsaved changes (E37); :enew! discards them."
    ),
    "delete": (
        ":[range]d [x] [n]  Delete lines into register x (default: unnamed)\n"
        "\n"
        "A number is a count: :d 3 deletes three lines from the cursor,\n"
        ":5d a 2 deletes lines 5-6 into register a"
    ),
    "yank": ":[range]y [x] [n]  Yank lines into register x (n: a count, as :d)",
    "move": ":[range]m {n}  Move lines below line n (0 = top, $ = end, . = cursor,\n"
            "               +1 / -2 relative: :m+1 moves the line down one)",
    "copy": ":[range]t {n}  Copy lines below line n (also :co, :copy)",
    "undo": ":undo / :redo  One undo / redo step (also u / Ctrl-R)",
    "registers": ":reg [x...]  Show register contents (also :registers, :di)",
    "marks": ":marks  Show marks with their line numbers",
    "find": (
        ":find pattern  Jump to next card matching pattern\n"
        "\n"
        "n / N repeat the last pattern forward / backward"
    ),
    "search": (
        ":search [query]  Open the card database search overlay\n"
        "\n"
        "Works like o: the chosen card is added below the cursor, in the\n"
        "cursor's zone. The query is pre-filled and uses the Scryfall-style\n"
        "syntax (t:creature c:g mv<=3 ...); see docs/search.md."
    ),
    "export": (
        ":export format [file]  Export deck "
        "(arena/mtgo/dek/moxfield/archidekt/vimtg/guide)\n"
        "\n"
        "No file: the export is copied to the clipboard. An existing\n"
        "file needs :export! to overwrite; the open deck's own file is\n"
        "never overwritten.\n"
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
        ":import [file|url]  Import a deck into a new unnamed buffer\n"
        "\n"
        "The imported deck opens in place of this one, unsaved, as the\n"
        "greeter's import does: the deck that was open is left as it is\n"
        "on disk, and the first :w names the new file after // Deck:.\n"
        "Unsaved changes refuse with E37; :import! discards them.\n"
        "With no argument the decklist (or deck URL) is read from the\n"
        "system clipboard. To ADD a pasted list to the deck instead,\n"
        "paste it in normal mode (your terminal's paste key).\n"
        "Files auto-detect their format: vimtg, MTGO text or .dek,\n"
        "Arena (MTGA), Moxfield CSV, Archidekt CSV. A deck URL from\n"
        "Moxfield, Archidekt, ManaBox, Deckstats, TappedOut, or\n"
        "MTGGoldfish fetches the list from the site: commander,\n"
        "companion, sideboard, and maybeboard land in their own zones,\n"
        "Archidekt user categories become @categories, and the URL is\n"
        "remembered as // Source:."
    ),
    "clipboard": (
        ":clipboard [format]  Copy deck to the system clipboard\n"
        "\n"
        "Default format is arena. mtgo, dek, moxfield, archidekt, vimtg,\n"
        "and guide also work, as with :export.\n"
        "Uses pbcopy, wl-copy, xclip, xsel or clip.exe when available\n"
        "(confirmed copy); otherwise asks the terminal via OSC 52, which\n"
        "cannot be confirmed (iTerm2, kitty, Alacritty, Wezterm and\n"
        "Windows Terminal support it). Over SSH OSC 52 is tried first."
    ),
    "sync": (
        ":sync[!]  Download Scryfall card data in the background\n"
        "\n"
        "Progress shows in the status line; editing continues meanwhile.\n"
        "Cached data newer than 7 days is reused; :sync! re-downloads.\n"
        "The status line shows how old the card data is."
    ),
    "filter": (
        ":filter expr  Show the cards whose @category matches expr\n"
        "(the others are dimmed). Space f opens the same prompt.\n"
        "\n"
        ":filter ramp              cards in @ramp\n"
        ":filter ramp|draw         OR (either category)\n"
        ":filter -removal          NOT (every card but @removal)\n"
        ":filter ramp -removal     AND NOT\n"
        ":filter / :filter!        clear filter\n"
        "\n"
        "Tab completes a category from the deck, most used first."
    ),
    "dtag": (
        ":dtag name...  Add deck-level tags to the // Tags: metadata line\n"
        "\n"
        ":dtag aggro          tag the deck aggro\n"
        ":dtag burn budget    add two tags at once\n"
        "\n"
        "The // Tags: line is created when the deck has none."
    ),
    "duntag": (
        ":duntag name...  Remove deck-level tags from the // Tags: line\n"
        "\n"
        "The emptied // Tags: line stays, so i can refill it."
    ),
    "help": ":help [command]  Open the help window (also F1; q closes)",
    "messages": (
        ":messages  Show recent messages and errors (alias :mes)\n"
        "\n"
        "Status messages vanish at the next key (errors stay up while\n"
        "you move the cursor); :messages lists the last 100 again.\n"
        ":messages clear  empties the list"
    ),
    "tutor": (
        ":Tutor[!]  The vimtg tutor, a lesson deck to practice in\n"
        "\n"
        "Opens a fresh copy of the lesson deck in a throwaway sandbox with\n"
        "its own small card database and default settings, so it works\n"
        "offline and never touches your decks. The same as `vimtg tutor`\n"
        "or t on the greeter. Unsaved changes need :Tutor! to drop."
    ),
    "tips": (
        ":tips [on|off]  The getting-started tips panel\n"
        "\n"
        ":tips      show the tips now (Esc hides them)\n"
        ":tips off  stop showing them under empty decks (remembered)\n"
        ":tips on   show them again under empty decks\n"
        "\n"
        "Under an empty deck they stay up through its first cards until\n"
        "the first :w."
    ),
    "history": (
        ":history  Open the lazygit-style history overlay (also gh)\n"
        "\n"
        "A floating window over the editor with four panels:\n"
        "  1 Working copy   uncommitted changes vs the latest snapshot\n"
        "  2 Snapshots      3 Diff   4 Stats\n"
        "\n"
        "Keybindings in the overlay:\n"
        "  1-4 / Tab      Jump to / cycle panels\n"
        "  j/k / wheel    Navigate or scroll\n"
        "  gg/G  Ctrl-D/U Top/bottom, half page\n"
        "  Enter          Open the item in the Diff panel\n"
        "  c              Commit snapshot\n"
        "  t/T            Tag/untag snapshot (Snapshots panel)\n"
        "  R              Restore snapshot (Snapshots panel)\n"
        "  d              Toggle unchanged cards in the diff\n"
        "  q / Esc / gh   Return to editor\n"
        "  ? / F1         This topic / full help"
    ),
    "commit": ":commit message  Create a named snapshot of current deck state",
    "checkpoint": (
        ":checkpoint name  Commit the current state and tag it\n"
        "\n"
        "Shorthand for :commit followed by tagging the new snapshot."
    ),
    "stats": (
        ":stats  One-line deck summary on the command line\n"
        "\n"
        "Card count, average CMC, cards per type, and the total price\n"
        "with its source. Without card data it counts the card lines in\n"
        "each zone. :analytics shows the curve, colors, and mana base."
    ),
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
        ":map ; :w        ';' saves\n"
        ":map              list mappings\n"
        "Persist mappings in ~/.config/vimtg/config.toml [keybindings]."
    ),
    "unmap": ":unmap key  Remove a key remapping",
    "home": ":home  Return to the greeter (:home! discards changes)",
    "vsplit": (
        ":vsplit deck-file  Open another deck beside this one (alias :vsp, :vs)\n"
        "\n"
        "The split pane is read-only — compare a netdeck or an old\n"
        "version while editing. Ctrl-W w switches pane focus (j/k scroll,\n"
        "q closes, Esc returns), Ctrl-W c / :close closes it."
    ),
    "split": (
        ":split deck-file  Open another deck below this one (alias :sp, :hsplit)\n"
        "\n"
        "Horizontal variant of :vsplit — same keys: Ctrl-W w switch, :close close."
    ),
    "close": ":close  Close the split pane (alias :only; also Ctrl-W c)",
    "edhrec": (
        ":edhrec [type]  EDHREC recommendations for the commander (alias :rec)\n"
        "\n"
        "Commander decks only: uses the CMD: line(s), partner pairs\n"
        "included. Opens a side pane with one tab per card type;\n"
        "the optional argument jumps to a tab (creature, instant,\n"
        "sorcery, artifact, enchantment, planeswalker, battle, land).\n"
        "\n"
        "In the pane: j/k select, h/l switch tabs, Enter adds the\n"
        "card to the deck, q closes the pane, Esc returns to the\n"
        "editor. ✓ marks cards already in the deck. Results are\n"
        "cached for 7 days."
    ),
    "analytics": (
        ":analytics  Live deck-analytics pane (alias :ana; Space a toggles it)\n"
        "\n"
        "Mana curve, card counts per type / zone / category, a\n"
        "mana-base check (colored sources vs pip requirements, a\n"
        "Karsten-style heuristic scaled to deck size), and draw\n"
        "odds. The odds line follows the cursor: put it on a card\n"
        "to see the chance of drawing one by the opener or turn 3.\n"
        "Everything recomputes as the deck is edited.\n"
        "\n"
        "Ctrl-W w focuses the pane (j/k scroll, q close, Esc back)."
    ),
    "hand": (
        ":hand [seed=N]  Sample hand / goldfish overlay (alias :goldfish;\n"
        "also Space h)\n"
        "\n"
        "Shuffles the main deck and draws an opening seven. Sideboard,\n"
        "maybeboard, commander and companion cards stay out of the\n"
        "library; the commander is shown in the command zone. With a\n"
        "sideboard plan active the post-board deck is used. seed=N\n"
        "makes the shuffles repeatable.\n"
        "\n"
        "Keys: n/Space draw, m mulligan (London: draw 7, then b puts\n"
        "the selected card on the bottom), j/k (gg/G, Ctrl-D/U) select,\n"
        "r reshuffle, ? this help, q/Esc close. The first mulligan is\n"
        "free in Commander and Brawl. Shows the land count in hand and\n"
        "the odds of 1+ / 2+ lands in seven and of hitting every land\n"
        "drop by turn N."
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

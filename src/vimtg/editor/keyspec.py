"""The editor keymap, declared once.

Every key the vim engine understands is listed here with its meaning and
group. The which-key popup, the help overview, and the drift tests in
tests/editor/test_keyspec.py all read this table, so a key cannot be
handled without being documented, or documented without being handled.

Prefix namespaces (normal mode), each with one meaning:

    g   go / global      gg gc gC gl gh g?
    t   tags             ta tr tt tf tl tc tn tp
    S   splits & panes   Sv Sh Ss Sc Sr Sa Sd
    z   zones & scroll   zs zm zd zc zp  zi zo  zz zt zb
    m   marks (set)      m{a-z}
    '   marks (jump)     '{a-z}
    q   macros (record)  q{a-z}, q stops
    @   macros (play)    @{a-z} @@
    "   registers        "{a-z} "{A-Z} "0 "1-9 "_ "+ "*
    [ ] jumps            [[ ]] [v ]v
    Z   quit             ZZ ZQ
"""

from __future__ import annotations

from dataclasses import dataclass

MARK = "{a-z}"


@dataclass(frozen=True)
class KeyBinding:
    """One documented binding.

    keys: the sequences as typed (patterns use {a-z}); several keys share
    one row when they are a natural pair, e.g. ("j", "k").
    label: how the row is shown; defaults to the keys joined with "/".
    completes: False for keys that only start a sequence (operators, the
    register prefix), which the drift test expects to leave the keymap
    pending rather than complete.
    quick: which-key fallback section this row belongs to, if any.
    """

    keys: tuple[str, ...]
    action: str
    group: str
    mode: str = "normal"
    note: str = ""
    label: str = ""
    completes: bool = True
    quick: str = ""
    shorts: tuple[str, ...] = ()  # which-key label per key, when the row is a pair
    brief: str = ""  # short description for the which-key cheat sheet

    @property
    def shown(self) -> str:
        return "/".join(self.keys)

    @property
    def quick_label(self) -> str:
        return self.label or self.shown

    @property
    def display(self) -> str:
        """Help-overview spelling: Esc / F1 / Ctrl-D/U for named keys."""
        if self.label and self.label != "S":
            return self.label
        return self.shown


def _b(
    keys: str | tuple[str, ...], action: str, group: str, *,
    mode: str = "normal", note: str = "", label: str = "",
    completes: bool = True, quick: str = "", shorts: tuple[str, ...] = (),
    brief: str = "",
) -> KeyBinding:
    return KeyBinding(
        keys=(keys,) if isinstance(keys, str) else keys,
        action=action, group=group, mode=mode, note=note, label=label,
        completes=completes, quick=quick, shorts=shorts, brief=brief,
    )


NAVIGATION = "NAVIGATION"
EDITING = "EDITING"
ZONES = "ZONES"
MARKS_MACROS = "MARKS, MACROS & REGISTERS"
VISUAL = "VISUAL MODE"
CATEGORIES = "CATEGORIES"
CMDLINE = "COMMAND LINE"
SPLITS = "SPLITS, EDHREC & ANALYTICS"
TAGS = "TAGS"
VCS = "VERSION CONTROL"
MODES = "MODES"

EDITOR_BINDINGS: tuple[KeyBinding, ...] = (
    # ── Modes ─────────────────────────────────────────────
    _b("i", "Edit the current line", MODES, quick="Editing", brief="edit line",
       note="On // Key: metadata lines only the value is editable; "
            "the // Format: value Tab-completes known formats"),
    _b("A", "Add or edit the card's inline comment (empty removes)", MODES,
       quick="Editing", brief="comment card"),
    _b(("o", "O"), "Add a card below / above (opens card search)", MODES, quick="Editing",
       brief="add card",
       note="The card joins the zone under the cursor: inside a CMD:/SB: "
            "block it lands there; in the mainboard it auto-files by type. "
            "A count sets copies: 4o adds four. Inside a VS: plan it writes "
            "a signed plan line"),
    _b(("v", "V"), "Visual / visual-line selection", MODES, quick="Commands", brief="visual mode"),
    _b(":", "Ex command line", MODES, quick="Commands", brief="command mode"),
    _b(("/", "?"), "Search forward / backward for a card (regex)", MODES,
       label="/ ?", quick="Commands", brief="search",
       note="An empty pattern repeats the last one; Up/Down recall earlier searches"),
    _b("escape", "Back to normal mode; cancels a pending sequence", MODES, label="Esc"),
    _b("f1", "Full-screen help (also :help)", MODES, label="F1", quick="Commands",
       brief="help"),
    _b("g?", "Toggle the quick-reference panel", MODES, shorts=("quick reference",)),
    _b(("ZZ", "ZQ"), "Save if changed, then quit (:x) / quit discarding changes (:q!)", MODES,
       shorts=("save and quit", "quit without saving")),
    # ── Navigation ────────────────────────────────────────
    _b(("j", "k"), "Move down / up (blank lines skipped)", NAVIGATION, quick="Navigation",
       brief="down/up"),
    _b(("gg", "G"), "First / last line; {n}G or {n}gg goes to line n", NAVIGATION,
       quick="Navigation", shorts=("go to top", "go to bottom"), brief="top/bottom"),
    _b(("w", "b"), "Next / previous card entry", NAVIGATION, quick="Navigation",
       brief="next/prev card"),
    _b(("{", "}"), "Prev/next section", NAVIGATION, quick="Navigation", brief="prev/next section"),
    _b(("[[", "]]"), "Prev/next section or plan header", NAVIGATION, quick="Navigation",
       shorts=("prev section header", "next section header"), brief="prev/next header"),
    _b(("[v", "]v"), "Previous / next sideboard plan (activates it)", NAVIGATION,
       shorts=("prev sideboard plan", "next sideboard plan")),
    _b(("ctrl_d", "ctrl_u"), "Half page down / up", NAVIGATION, label="Ctrl-D/U",
       quick="Navigation", brief="half page"),
    _b(("H", "M", "L"), "Top / middle / bottom of the visible deck view", NAVIGATION,
       note="A count offsets H and L: 3H is the third visible line"),
    _b(("n", "N"), "Repeat the last search in the same / opposite direction", NAVIGATION,
       quick="Navigation", brief="next/prev match"),
    _b(("*", "#"), "Search forward / backward for the card under the cursor", NAVIGATION,
       note="The whole name: * on Shock never stops on Shock Troops"),
    _b(("zz", "zt", "zb"), "Scroll the cursor line to the center / top / bottom", NAVIGATION,
       shorts=("scroll: center", "scroll: top", "scroll: bottom")),
    # ── Editing ───────────────────────────────────────────
    _b("dd", "Delete the card line", EDITING, quick="Editing", brief="delete card"),
    _b("yy", "Yank (copy) the card line", EDITING, quick="Editing", brief="yank card"),
    _b("cc", "Change the line (delete, then card search)", EDITING),
    _b(("d", "y", "c"), "Operators: compose with a motion (dw, d}, y5G)", EDITING,
       completes=False,
       note="w b { } [[ ]] are exclusive: dw deletes this card, d} stops at "
            "the end of the section. j k G gg take whole lines"),
    _b("x", "Delete the card under the cursor (into the register)", EDITING),
    _b(("p", "P"), "Paste below / above", EDITING, quick="Editing", brief="paste below/above"),
    _b(("+", "-"), "Increment / decrement quantity (- at 0 deletes)", EDITING,
       quick="Editing", brief="inc/dec quantity"),
    _b(".", "Repeat the last change", EDITING, quick="Editing", brief="repeat last",
       note="Every edit repeats: operators (c with the card it added), o/O with "
            "their card, p, +/-, x, zone and plan moves, tags, categories, "
            "comments, i, and :s; a visual change repeats on as many lines"),
    _b(("u", "ctrl_r"), "Undo / redo", EDITING, label="u / Ctrl-R", quick="Commands",
       brief="undo/redo"),
    # ── Zones (z prefix) ──────────────────────────────────
    _b("zs", "Move the card to the sideboard", ZONES, shorts=("→ sideboard",),
       note="All copies; 2zs splits off two. Zone moves keep category, tags, and "
            "comment. zc is refused outside commander formats"),
    _b("zm", "Move the card to the maybeboard", ZONES, shorts=("→ maybeboard",)),
    _b("zd", "Move the card to the main deck", ZONES, shorts=("→ main deck",)),
    _b("zc", "Move the card to the command zone (CMD:)", ZONES, shorts=("→ commander",)),
    _b("zp", "Move the card to the companion slot (CMP:)", ZONES, shorts=("→ companion",)),
    _b("zo", "Board the card out of the active sideboard plan", ZONES, shorts=("board out (plan)",),
       note="All copies; 2zo boards two. See :plan"),
    _b("zi", "Board the card into the active sideboard plan", ZONES, shorts=("board in (plan)",)),
    # ── Marks, macros, registers ──────────────────────────
    _b(f"m{MARK}", "Set a mark (all 26 letters)", MARKS_MACROS, shorts=("set mark",)),
    _b(f"'{MARK}", "Jump to a mark", MARKS_MACROS, shorts=("jump to mark",)),
    _b((f"q{MARK}", "q"), "Record a macro / stop recording", MARKS_MACROS, quick="Commands",
       note="qA-qZ append to the macro", shorts=("record macro", "stop recording"),
       brief="record macro"),
    _b((f"@{MARK}", "@@"), "Play a macro / replay the last one", MARKS_MACROS,
       shorts=("play macro", "replay last")),
    _b(f'"{MARK}', "Use a named register for the next yank, delete, or put", MARKS_MACROS,
       completes=False, note='"A-Z appends, "0 is the yank register, "1-9 the delete history',
       shorts=("named register",)),
    _b('"_', "Black hole register: delete without touching any register", MARKS_MACROS,
       completes=False, shorts=("black hole",)),
    _b(('"+', '"*'), "Clipboard register: yanks and deletes also copy to the system clipboard",
       MARKS_MACROS, completes=False, shorts=("clipboard", "clipboard"),
       note='Copies via OSC52; "+p puts what was last yanked to it in this session'),
    # ── Visual mode ───────────────────────────────────────
    _b(("d", "y", "c"), "Delete / yank / change the selection", VISUAL, mode="visual"),
    _b("x", "Delete the selection (same as d)", VISUAL, mode="visual"),
    _b(("+", "-"), "Increment / decrement every card in the selection", VISUAL, mode="visual"),
    _b(("zs", "zm", "zd", "zc", "zp"), "Move every selected card to a zone", VISUAL,
       mode="visual"),
    _b(("zi", "zo"), "Board every selected card in / out of the active plan", VISUAL,
       mode="visual"),
    _b("o", "Jump to the other end of the selection", VISUAL, mode="visual"),
    _b("escape", "Exit visual mode", VISUAL, mode="visual", label="Esc"),
    # ── Categories ────────────────────────────────────────
    _b("gc", "Set the card's category (Tab completes)", CATEGORIES, shorts=("set category",)),
    _b("gC", "Clear the card's category", CATEGORIES, shorts=("clear category",)),
    _b("gl", "Toggle layout: by type / by category", CATEGORIES, shorts=("toggle layout",)),
    # ── Splits, EDHREC, analytics (S prefix) ──────────────
    _b(("Sv", "Sh"), "Open a vertical / horizontal split (prompts for a deck)", SPLITS,
       quick="Commands", label="S", shorts=("vertical split", "horizontal split"),
       brief="splits/EDHREC"),
    _b("Sr", "EDHREC recommendations for the commander (:edhrec)", SPLITS, shorts=("EDHREC recs",)),
    _b("Sa", "Live analytics pane (:analytics)", SPLITS, shorts=("analytics",)),
    _b("Sd", "Sample hand / goldfish overlay (:hand)", SPLITS, shorts=("sample hand",)),
    _b("Ss", "Switch focus between the editor and the pane", SPLITS, shorts=("switch pane",),
       note="In a pane: j/k move, gg/G top/bottom, Ctrl-D/U half page, "
            "h/l switch EDHREC tabs, Enter adds the selected card, Esc returns"),
    _b("Sc", "Close the split", SPLITS, shorts=("close split",)),
    # ── Tags (t prefix) ───────────────────────────────────
    _b("ta", "Add a tag to the card", TAGS, shorts=("add tag",)),
    _b("tr", "Remove a tag", TAGS, shorts=("remove tag",)),
    _b("tt", "Toggle a tag", TAGS, shorts=("toggle tag",)),
    _b("tf", "Filter the view by a tag expression", TAGS, shorts=("filter by tag",)),
    _b("tl", "List tags with counts", TAGS, shorts=("list tags",)),
    _b("tc", "Clear the card's tags", TAGS, shorts=("clear tags",)),
    _b(("tn", "tp"), "Next / previous card sharing a tag", TAGS,
       shorts=("next tagged", "prev tagged")),
    # ── Version control ───────────────────────────────────
    _b("gh", "Toggle the history overlay (lazygit-style)", VCS, shorts=("history overlay",)),
    # ── Command line (: and / ? prompts) ─────────────────
    _b(("up", "down"), "Recall older / newer history entries", CMDLINE, mode="cmdline",
       label="Up / Down",
       note="Matches what was typed before the first Up. Kept per prompt "
            "kind and saved in ~/.local/state/vimtg"),
    _b(("left", "right"), "Move the cursor", CMDLINE, mode="cmdline", label="Left / Right"),
    _b(("ctrl_b", "ctrl_e"), "Start / end of the line", CMDLINE, mode="cmdline",
       label="Ctrl-B / Ctrl-E"),
    _b("ctrl_w", "Delete the word before the cursor", CMDLINE, mode="cmdline",
       label="Ctrl-W"),
    _b("ctrl_u", "Delete everything before the cursor", CMDLINE, mode="cmdline",
       label="Ctrl-U"),
    _b("backspace", "Delete a character; on an empty line, leave the prompt", CMDLINE,
       mode="cmdline", label="Backspace"),
)

# Prefix → which-key menu title; every prefix the keymap pends on.
PREFIX_TITLES: dict[str, str] = {
    "g": "go", "t": "tags", "S": "splits", "z": "zones & scroll", "m": "marks",
    "'": "marks", "q": "macros", "@": "macros", '"': "registers",
    "[": "jump back", "]": "jump forward", "Z": "quit",
}

# Motions that may follow an operator, for the d / y / c which-key menus.
OPERATOR_MENU: tuple[tuple[str, str], ...] = (
    ("{op}{op}", "this line"), ("{op}w", "this card"),
    ("{op}}", "to end of section"), ("{op}G", "to end ({n}G: to line n)"),
)


def bindings(mode: str = "normal") -> tuple[KeyBinding, ...]:
    return tuple(b for b in EDITOR_BINDINGS if b.mode == mode)


def _menu_label(key: str) -> str:
    return key.replace("{", "").replace("}", "")


def which_key_menus() -> dict[str, list[tuple[str, str]]]:
    """Pending-key menus: every two-key normal binding grouped by prefix,
    plus the operator menus. The q menu only shows while nothing records
    (a bare q stops a recording at once), so it lists q{a-z} alone."""
    menus: dict[str, list[tuple[str, str]]] = {}
    for b in bindings("normal"):
        for i, key in enumerate(b.keys):
            if len(key) == 2 or key.endswith(MARK):
                prefix = key[0]
                if prefix in PREFIX_TITLES:
                    menus.setdefault(prefix, []).append((_menu_label(key), _short(b, i)))
    for op in ("d", "y", "c"):
        menus[op] = [
            (pattern.replace("{op}", op), desc) for pattern, desc in OPERATOR_MENU
        ]
    return menus


def _short(b: KeyBinding, index: int) -> str:
    """A which-key description for one key of a row."""
    if b.shorts:
        return b.shorts[min(index, len(b.shorts) - 1)]
    return b.action.partition(" (")[0]


def quick_hints() -> dict[str, list[tuple[str, str]]]:
    """The which-key fallback cheat sheet (no sequence pending)."""
    out: dict[str, list[tuple[str, str]]] = {"Navigation": [], "Editing": [], "Commands": []}
    for b in bindings("normal"):
        if b.quick:
            out[b.quick].append((b.quick_label, b.brief or b.action.partition(" (")[0]))
    return out


def overview_groups() -> list[tuple[str, list[KeyBinding]]]:
    """Help-overview sections in declaration order (normal, visual,
    and command line)."""
    groups: dict[str, list[KeyBinding]] = {}
    for b in EDITOR_BINDINGS:
        groups.setdefault(b.group, []).append(b)
    return list(groups.items())


def format_overview_group(title: str, rows: list[KeyBinding], width: int = 62) -> str:
    """One help section: a header line and `  keys  action` rows, notes wrapped."""
    import textwrap

    lines = [title]
    for b in rows:
        first = f"  {b.display:<13} {b.action}"
        lines.append(first)
        if b.note:
            lines.extend(
                textwrap.wrap(b.note, width=width, initial_indent=" " * 16,
                              subsequent_indent=" " * 16)
            )
    return "\n".join(lines)

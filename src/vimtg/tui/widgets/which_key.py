"""Which-key tooltip widget — shows available keybindings contextually.

Appears when a multi-key sequence is pending in NORMAL mode (operator,
register, count, or prefix key), showing what can follow. Inspired by
emacs which-key and vim's popup menu.
"""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.tui.theme import COLORS

# Fallback shown for pending states with no specific continuation
# (e.g. a count in progress).
NORMAL_HINTS = {
    "Navigation": [
        ("j/k", "down/up"),
        ("w/b", "next/prev card"),
        ("{/}", "prev/next section"),
        ("[[/]]", "prev/next header"),
        ("gg/G", "top/bottom"),
        ("Ctrl-D/U", "page down/up"),
    ],
    "Editing": [
        ("i", "edit line"),
        ("A", "comment card"),
        ("o/O", "add card"),
        ("dd", "delete card"),
        ("yy", "yank card"),
        ("p/P", "paste below/above"),
        ("+/-", "inc/dec quantity"),
        (".", "repeat last"),
    ],
    "Commands": [
        (":", "command mode"),
        ("/", "search"),
        ("u", "undo"),
        ("Ctrl-R", "redo"),
        ("v/V", "visual mode"),
        ("q{a-z}", "record macro"),
        ("S", "splits/EDHREC"),
    ],
}

PENDING_HINTS: dict[str, list[tuple[str, str]]] = {
    "d": [
        ("dd", "delete line"), ("dw", "del next card"),
        ("d}", "del section"), ("dG", "del to end"),
    ],
    "y": [
        ("yy", "yank line"), ("yw", "yank next card"),
        ("y}", "yank section"), ("yG", "yank to end"),
    ],
    "c": [("cc", "change line"), ("cw", "change to next card")],
    "g": [
        ("gg", "go to top"), ("gc", "set category"),
        ("gC", "clear category"), ("gl", "toggle layout"),
    ],
    "[": [("[[", "prev section header")],
    "]": [("]]", "next section header")],
    "\"": [("\"a-z", "named register"), ("\"0", "yank register"), ("\"1-9", "delete history")],
    "q": [("qa-z", "record macro"), ("q (stop)", "stop recording")],
    "@": [("@a-z", "play macro"), ("@@", "replay last")],
    "m": [
        ("ms", "→ sideboard"), ("mm", "→ maybeboard"), ("md", "→ main deck"),
        ("mc", "→ commander"), ("mp", "→ companion"),
        ("ma-z", "set mark"),
    ],
    "'": [("'a-z", "jump to mark")],
    "S": [
        ("Sv", "vertical split"), ("Sh", "horizontal split"),
        ("Sr", "EDHREC recs"), ("Ss", "switch pane"), ("Sc", "close split"),
    ],
    "t": [
        ("ta", "add tag"), ("tr", "remove tag"), ("tt", "toggle tag"),
        ("tf", "filter by tag"), ("tl", "list tags"), ("tc", "clear tags"),
        ("tn", "next tagged"), ("tp", "prev tagged"),
    ],
}


class WhichKey(Static):
    """Context-sensitive keybinding tooltip overlay."""

    pending_key: reactive[str] = reactive("")

    def render(self) -> Text:
        # Show pending key hints if we're mid-sequence
        if self.pending_key and self.pending_key in PENDING_HINTS:
            return self._render_hints({"Next": PENDING_HINTS[self.pending_key]})
        return self._render_hints(NORMAL_HINTS)

    def _render_hints(self, hints: dict[str, list[tuple[str, str]]]) -> Text:
        t = Text()
        sep = f"dim {COLORS['comment']}"
        t.append("─" * 60 + "\n", style=sep)

        for section, keys in hints.items():
            t.append(f" {section}: ", style=f"bold {COLORS['mana_blue']}")
            parts = []
            for key, desc in keys:
                part = Text()
                part.append(key, style=f"bold {COLORS['quantity']}")
                part.append(f" {desc}", style="dim")
                parts.append(part)
            for i, part in enumerate(parts):
                t.append(part)
                if i < len(parts) - 1:
                    t.append("  ", style="dim")
            t.append("\n")

        return t

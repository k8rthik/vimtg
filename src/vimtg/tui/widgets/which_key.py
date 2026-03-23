"""Which-key tooltip widget — shows available keybindings contextually.

Appears at the bottom of the screen after a short delay when the user
is in NORMAL mode, showing what keys are available. Inspired by emacs
which-key and vim's popup menu.
"""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.editor.modes import Mode
from vimtg.tui.theme import COLORS

NORMAL_HINTS = {
    "Navigation": [
        ("j/k", "down/up"),
        ("w/b", "next/prev card"),
        ("{/}", "next/prev section"),
        ("[[/]]", "prev/next header"),
        ("gg/G", "top/bottom"),
        ("Ctrl-D/U", "page down/up"),
    ],
    "Editing": [
        ("i/o/O", "insert mode"),
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
    ],
}

INSERT_HINTS = {
    "Insert Mode": [
        ("Esc", "back to normal"),
        ("Ctrl-N", "next result"),
        ("Ctrl-P", "prev result"),
        ("Enter", "confirm card"),
        ("Tab", "next result"),
    ],
}

COMMAND_HINTS = {
    "Commands": [
        (":w", "save"),
        (":q", "quit"),
        (":sort", "sort cards"),
        (":s/a/b/g", "substitute"),
        (":g/pat/d", "global delete"),
        (":help", "show help"),
        (":export", "export deck"),
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
    "g": [("gg", "go to top")],
    "[": [("[[", "prev section header")],
    "]": [("]]", "next section header")],
    "\"": [("\"a-z", "named register"), ("\"0", "yank register"), ("\"1-9", "delete history")],
    "q": [("qa-z", "record macro"), ("q (stop)", "stop recording")],
    "@": [("@a-z", "play macro"), ("@@", "replay last")],
}


class WhichKey(Static):
    """Context-sensitive keybinding tooltip overlay."""

    mode: reactive[Mode] = reactive(Mode.NORMAL)
    pending_key: reactive[str] = reactive("")
    visible: reactive[bool] = reactive(False)

    def render(self) -> Text:
        if not self.visible:
            return Text("")

        # Show pending key hints if we're mid-sequence
        if self.pending_key and self.pending_key in PENDING_HINTS:
            return self._render_hints({"Next": PENDING_HINTS[self.pending_key]})

        # Show mode-appropriate hints
        hints = NORMAL_HINTS
        if self.mode == Mode.INSERT:
            hints = INSERT_HINTS
        elif self.mode in (Mode.COMMAND, Mode.SEARCH):
            hints = COMMAND_HINTS

        return self._render_hints(hints)

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

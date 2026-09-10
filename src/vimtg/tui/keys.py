"""Shared key vocabulary for every screen and pane outside the vim editor.

One meaning per key, whichever screen is open:

    j / k / ↓ / ↑      move one line
    Ctrl-D / Ctrl-U    half a page
    gg / G, Home / End top / bottom
    q / Esc            close the screen (Esc cancels an open prompt first)
    ? / F1             help for this screen / full help
    mouse wheel        scrolls whatever is under the pointer

`VimNav` parses the navigation keys with a pending `g`, so `gg` is top
everywhere and a bare `g` never is. `render_hints` draws every hint bar
the same way, and `display_key` spells key names the same way.
"""

from __future__ import annotations

from rich.text import Text

from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scrolling import scroll_step_for_key

NAV_DOWN = frozenset({"j", "down"})
NAV_UP = frozenset({"k", "up"})
HALF_DOWN = "ctrl_d"
HALF_UP = "ctrl_u"
TOP_KEYS = frozenset({"home"})  # plus gg via VimNav
BOTTOM_KEYS = frozenset({"G", "end"})
CLOSE_KEYS = frozenset({"q", "escape"})
HELP_KEY = "?"
FULL_HELP_KEY = "f1"

PENDING = "pending"

Hint = tuple[str, str]

_DISPLAY = {
    "ctrl_d": "Ctrl-D", "ctrl_u": "Ctrl-U", "ctrl_r": "Ctrl-R",
    "ctrl_j": "Ctrl-J", "ctrl_k": "Ctrl-K", "ctrl_n": "Ctrl-N", "ctrl_p": "Ctrl-P",
    "escape": "Esc", "enter": "Enter", "tab": "Tab", "shift_tab": "Shift-Tab",
    "backspace": "Backspace", "f1": "F1", " ": "Space",
    "home": "Home", "end": "End", "up": "Up", "down": "Down",
    "left": "Left", "right": "Right",
}


def display_key(key: str) -> str:
    """The one spelling of a translated key name used in every hint."""
    return _DISPLAY.get(key, key)


class VimNav:
    """Navigation-key parser shared by every list and viewer.

    feed() returns what scroll_step_for_key returns — a signed line delta,
    "home", "end" — plus PENDING after a first `g`, and None for keys that
    are not navigation. A pending `g` followed by anything but `g` is
    dropped and the second key is parsed normally, so `g` then `q` still
    closes a screen.
    """

    def __init__(self) -> None:
        self.pending_g = False

    def feed(self, key: str, viewport: int) -> int | str | None:
        if self.pending_g:
            self.pending_g = False
            if key == "g":
                return "home"
        elif key == "g":
            self.pending_g = True
            return PENDING
        return scroll_step_for_key(key, viewport)

    def reset(self) -> None:
        self.pending_g = False


NAV_HINTS: tuple[Hint, ...] = (
    ("j/k", "move"), ("gg/G", "top/bottom"), ("Ctrl-D/U", "half page"),
)


def render_hints(hints: tuple[Hint, ...] | list[Hint], width: int = 0, leading: str = " ") -> Text:
    """A hint bar: `key desc  key desc …`, keys bold, descriptions dim.

    When `width` is known and the full bar would not fit, descriptions
    are dropped so every key stays visible.
    """
    t = Text()
    full_len = len(leading) + sum(len(k) + len(d) + 3 for k, d in hints)
    compact = 0 < width < full_len
    t.append(leading)
    for i, (key, desc) in enumerate(hints):
        t.append(key, style=f"bold {COLORS['quantity']}")
        if not compact:
            t.append(f" {desc}", style="dim")
        if i < len(hints) - 1:
            t.append("  ", style="dim")
    return t

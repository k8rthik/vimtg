"""First-run tips — a short "how do I do anything" panel.

Shown under an empty deck, and on through its first cards until the
first :w, until the user turns it off with `:tips off`; Esc closes it
for the session and `:tips` brings it back. Everything here also lives at the top of :help ("GETTING
STARTED"), so dismissing it loses nothing.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from vimtg.tui.theme import COLORS

TIPS: tuple[tuple[str, str], ...] = (
    ("o", "add a card: type part of its name, Enter picks it"),
    ("j / k", "move down / up;  +/- change the quantity"),
    (":w", "save    :q quit    :q! quit without saving"),
    ("F1", "full help (also :help);  g? cheat sheet"),
)


def render_tips() -> Text:
    t = Text()
    t.append(" Getting started", style=f"bold {COLORS['mana_blue']}")
    t.append("  (Esc hides, :tips off for good)\n", style=f"dim {COLORS['comment']}")
    for key, text in TIPS:
        t.append(f"  {key:<7}", style=f"bold {COLORS['quantity']}")
        t.append(f"{text}\n")
    t.append("  Normal mode moves and edits; i / o type text; Esc returns.",
             style="dim")
    return t


class TipsPanel(Static):
    """The tips text; MainScreen decides when it is displayed."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(render_tips(), *args, **kwargs)  # type: ignore[arg-type]

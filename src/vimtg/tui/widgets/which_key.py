"""Which-key tooltip widget — shows available keybindings contextually.

Appears when a multi-key sequence is pending in NORMAL mode (operator,
register, count, or prefix key), showing what can follow. Inspired by
emacs which-key and vim's popup menu.
"""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.editor.keyspec import quick_hints, which_key_menus
from vimtg.tui.theme import COLORS

# Both tables are derived from the editor key spec, the single source of
# truth for what every key does (src/vimtg/editor/keyspec.py).
NORMAL_HINTS: dict[str, list[tuple[str, str]]] = quick_hints()
PENDING_HINTS: dict[str, list[tuple[str, str]]] = which_key_menus()


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

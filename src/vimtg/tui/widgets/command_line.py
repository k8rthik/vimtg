"""CommandLine widget — displays : commands, / searches, and status messages."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.tui.theme import COLORS


class CommandLine(Static):
    """Bottom-most line for command entry, fuzzy completion ghost, and status."""

    prefix: reactive[str] = reactive("")
    text: reactive[str] = reactive("")
    message: reactive[str] = reactive("")
    ghost: reactive[str] = reactive("")  # Inline fuzzy completion preview

    def render(self) -> Text:
        if self.message:
            return Text(f" {self.message}", style="dim")
        if self.prefix:
            t = Text(f" {self.prefix}")
            t.append(self.text, style="bold")
            # Show ghost completion inline after the typed text
            if self.ghost and self.ghost.lower().startswith(self.text.lower()):
                remaining = self.ghost[len(self.text) :]
                t.append(remaining, style=f"dim {COLORS['comment']}")
            elif self.ghost:
                t.append(f"  → {self.ghost}", style=f"dim {COLORS['comment']}")
            return t
        return Text(
            " Press ? for help  |  : command  |  i insert  |  o add card",
            style="dim",
        )

    def show(self, prefix: str) -> None:
        """Activate command input with the given prefix (: or /)."""
        self.prefix = prefix
        self.text = ""
        self.message = ""
        self.ghost = ""

    def hide(self) -> None:
        """Clear and hide command input."""
        self.prefix = ""
        self.text = ""
        self.ghost = ""

    def set_message(self, msg: str) -> None:
        """Display a transient status message."""
        self.prefix = ""
        self.text = ""
        self.ghost = ""
        self.message = msg

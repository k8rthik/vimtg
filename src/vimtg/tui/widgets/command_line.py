"""CommandLine widget — displays : commands, / searches, and status messages."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.tui.theme import COLORS

# Single source for the idle hint — main_screen shows the same string
GENERIC_HINT = "Press ? for help  |  : command  |  o add card  |  i edit line"


class CommandLine(Static):
    """Bottom-most line for command entry, fuzzy completion ghost, and status."""

    prefix: reactive[str] = reactive("")
    text: reactive[str] = reactive("")
    message: reactive[str] = reactive("")
    error: reactive[bool] = reactive(False)  # Style `message` as an error
    ghost: reactive[str] = reactive("")  # Inline fuzzy completion preview
    hint: reactive[str] = reactive("")  # Context-sensitive persistent hint
    cursor_pos: reactive[int] = reactive(0)  # Cursor position within text

    def render(self) -> Text:
        if self.message:
            if self.error:
                return Text(f" {self.message}", style=f"bold {COLORS['error']}")
            return Text(f" {self.message}", style="dim")
        if self.prefix or self.text:
            t = Text(f" {self.prefix}")
            pos = min(self.cursor_pos, len(self.text))
            before = self.text[:pos]
            after = self.text[pos:]
            t.append(before, style="bold")
            if after:
                t.append(after[0], style="bold reverse")
                t.append(after[1:], style="bold")
            else:
                # Cursor at end — show block cursor
                t.append(" ", style="reverse")
            # Ghost completion only when cursor is at end
            if pos >= len(self.text):
                if self.ghost and self.ghost.lower().startswith(self.text.lower()):
                    remaining = self.ghost[len(self.text) :]
                    t.append(remaining, style=f"dim {COLORS['comment']}")
                elif self.ghost:
                    t.append(f"  \u2192 {self.ghost}", style=f"dim {COLORS['comment']}")
            return t
        if self.hint:
            return Text(f" {self.hint}", style="dim")
        return Text(f" {GENERIC_HINT}", style="dim")

    def show(self, prefix: str) -> None:
        """Activate command input with the given prefix (: or /)."""
        self.prefix = prefix
        self.text = ""
        self.message = ""
        self.error = False
        self.ghost = ""
        self.cursor_pos = 0

    def hide(self) -> None:
        """Clear and hide command input."""
        self.prefix = ""
        self.text = ""
        self.ghost = ""
        self.cursor_pos = 0

    def set_message(self, msg: str, *, error: bool = False) -> None:
        """Display a transient status message; errors render highlighted."""
        self.prefix = ""
        self.text = ""
        self.ghost = ""
        self.cursor_pos = 0
        self.message = msg
        self.error = error

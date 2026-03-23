"""CommandLine widget — displays : commands, / searches, and status messages."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static


class CommandLine(Static):
    """Bottom-most line for command entry and status messages."""

    prefix: reactive[str] = reactive("")
    text: reactive[str] = reactive("")
    message: reactive[str] = reactive("")

    def render(self) -> Text:
        if self.message:
            return Text(f" {self.message}", style="dim")
        if self.prefix:
            return Text(f" {self.prefix}{self.text}", style="bold")
        return Text(" Press ? for help  |  : command  |  i insert  |  o add card", style="dim")

    def show(self, prefix: str) -> None:
        """Activate command input with the given prefix (: or /)."""
        self.prefix = prefix
        self.text = ""
        self.message = ""

    def hide(self) -> None:
        """Clear and hide command input."""
        self.prefix = ""
        self.text = ""

    def set_message(self, msg: str) -> None:
        """Display a transient status message."""
        self.prefix = ""
        self.text = ""
        self.message = msg

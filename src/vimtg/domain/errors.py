"""Domain error hierarchy for vimtg.

Each error carries a Vim-style error code (e.g. E100) and a human-readable
message.  CLI and TUI layers catch VimTGError to display formatted feedback.
"""

from __future__ import annotations


class VimTGError(Exception):
    """Base error for all vimtg domain exceptions."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class DatabaseNotInitializedError(VimTGError):
    """Card database has not been synced yet."""

    def __init__(self) -> None:
        super().__init__("E100", "Card database not initialized (run 'vimtg sync' first)")


class CardNotFoundError(VimTGError):
    """Requested card does not exist in the database."""

    def __init__(self, name: str, suggestion: str | None = None) -> None:
        msg = f"Card not found: '{name}'"
        if suggestion:
            msg += f" (did you mean '{suggestion}'?)"
        super().__init__("E101", msg)


class DeckParseError(VimTGError):
    """Deck text could not be parsed at a specific line."""

    def __init__(self, line: int, detail: str) -> None:
        super().__init__("E102", f"Invalid deck format at line {line}: {detail}")


class UnsavedChangesError(VimTGError):
    """Operation requires saving first (mirrors Vim's E37)."""

    def __init__(self) -> None:
        super().__init__("E37", "No write since last change (add ! to override)")

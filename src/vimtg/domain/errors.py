"""Domain error hierarchy for vimtg.

Each error carries a Vim-style error code (e.g. E100) and a human-readable
message. CLI and TUI layers catch VimTGError to display formatted feedback.
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


class CardsNotFoundWarning(VimTGError):  # noqa: N818 — vim-style W-code, a warning not an error
    """Some imported cards could not be resolved against the database."""

    def __init__(self, count: int) -> None:
        super().__init__("W100", f"{count} cards not found in database")

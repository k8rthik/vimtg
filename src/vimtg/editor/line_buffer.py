"""Immutable single-line text buffer with cursor position.

Used by the KeyMap state machine for insert-mode and command-mode
text accumulation. All mutations return a new LineBuffer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineBuffer:
    """Immutable single-line text buffer with cursor."""

    text: str = ""
    cursor: int = 0

    @classmethod
    def from_text(cls, text: str) -> LineBuffer:
        """Create a LineBuffer with cursor at the end."""
        return cls(text=text, cursor=len(text))

    def insert(self, char: str) -> LineBuffer:
        """Insert a character at the cursor position."""
        new_text = self.text[:self.cursor] + char + self.text[self.cursor:]
        return LineBuffer(text=new_text, cursor=self.cursor + len(char))

    def delete_backward(self) -> LineBuffer:
        """Delete the character before the cursor (backspace)."""
        if self.cursor == 0:
            return self
        new_text = self.text[:self.cursor - 1] + self.text[self.cursor:]
        return LineBuffer(text=new_text, cursor=self.cursor - 1)

    def delete_forward(self) -> LineBuffer:
        """Delete the character at the cursor (delete key)."""
        if self.cursor >= len(self.text):
            return self
        new_text = self.text[:self.cursor] + self.text[self.cursor + 1:]
        return LineBuffer(text=new_text, cursor=self.cursor)

    def move_left(self) -> LineBuffer:
        """Move cursor one position left."""
        if self.cursor == 0:
            return self
        return LineBuffer(text=self.text, cursor=self.cursor - 1)

    def move_right(self) -> LineBuffer:
        """Move cursor one position right."""
        if self.cursor >= len(self.text):
            return self
        return LineBuffer(text=self.text, cursor=self.cursor + 1)

    def move_home(self) -> LineBuffer:
        """Move cursor to start of line."""
        return LineBuffer(text=self.text, cursor=0)

    def move_end(self) -> LineBuffer:
        """Move cursor to end of line."""
        return LineBuffer(text=self.text, cursor=len(self.text))

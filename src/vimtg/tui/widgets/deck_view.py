"""DeckView widget — renders the deck buffer with cursor and inline expansion.

Thin wrapper around deck_renderer; all formatting logic lives there.
"""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.tui.deck_renderer import render_line


class DeckView(Static):
    """Scrollable deck buffer display with inline card expansion."""

    buffer: reactive[Buffer | None] = reactive(None)
    cursor: reactive[Cursor] = reactive(Cursor)
    resolved_cards: reactive[dict[str, Card]] = reactive(dict)

    def render(self) -> Text:
        if self.buffer is None:
            return Text("No deck loaded", style="dim")

        output = Text()
        for i in range(self.buffer.line_count()):
            lines = render_line(i, self.buffer, self.cursor.row, self.resolved_cards)
            for line in lines:
                output.append(line)
                output.append("\n")
        return output

    def watch_buffer(self, _old: Buffer | None, _new: Buffer | None) -> None:
        self.refresh()

    def watch_cursor(self, _old: Cursor, _new: Cursor) -> None:
        self.refresh()

    def watch_resolved_cards(
        self, _old: dict[str, Card], _new: dict[str, Card]
    ) -> None:
        self.refresh()

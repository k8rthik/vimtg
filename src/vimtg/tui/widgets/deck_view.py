"""DeckView widget — renders the deck buffer with cursor and inline expansion.

Thin wrapper around deck_renderer; all formatting logic lives there.
"""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.card import Card
from vimtg.domain.tags import TagFilter, matches_filter
from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.tui.deck_renderer import render_line


class DeckView(Static):
    """Scrollable deck buffer display with inline card expansion."""

    buffer: reactive[Buffer | None] = reactive(None)
    cursor: reactive[Cursor] = reactive(Cursor)
    resolved_cards: reactive[dict[str, Card]] = reactive(dict)
    price_source: reactive[str] = reactive("usd")
    currency_symbol: reactive[str] = reactive("$")
    show_prices: reactive[bool] = reactive(True)
    show_line_numbers: reactive[bool] = reactive(True)
    auto_expand: reactive[bool] = reactive(True)
    tag_filter: reactive[TagFilter | None] = reactive(None)

    def render(self) -> Text:
        if self.buffer is None:
            return Text("No deck loaded", style="dim")

        output = Text()
        for i in range(self.buffer.line_count()):
            dimmed = (
                self.tag_filter is not None
                and self.buffer.is_card_line(i)
                and not matches_filter(self.buffer.tags_at(i), self.tag_filter)
            )
            lines = render_line(
                i, self.buffer, self.cursor.row, self.resolved_cards,
                show_line_numbers=self.show_line_numbers,
                price_source=self.price_source,
                currency_symbol=self.currency_symbol,
                show_prices=self.show_prices,
                auto_expand=self.auto_expand,
                dimmed=dimmed,
                width=self.size.width or None,
            )
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

    def watch_tag_filter(
        self, _old: TagFilter | None, _new: TagFilter | None
    ) -> None:
        self.refresh()

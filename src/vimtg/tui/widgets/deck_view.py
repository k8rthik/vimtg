"""DeckView widget — renders the deck buffer with cursor and inline expansion.

Thin wrapper around deck_renderer; all formatting logic lives there.
"""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.card import Card
from vimtg.domain.tags import TagFilter, matches_filter
from vimtg.domain.validation import ValidationError
from vimtg.editor.buffer import Buffer
from vimtg.editor.cursor import Cursor
from vimtg.editor.header_counts import HeaderCount, header_counts
from vimtg.tui.deck_renderer import render_line
from vimtg.tui.widgets.scrolling import compute_scroll_offset

_SCROLLOFF = 3


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
    line_errors: reactive[dict[int, ValidationError]] = reactive(dict)
    # Row -> -N/+N of the active sideboard plan (editor.plan_ops.row_deltas)
    plan_deltas: reactive[dict[int, int]] = reactive(dict)

    # Buffer-line scroll offset; follows the cursor. Expansion lines
    # under the cursor row may still clip at the very bottom edge —
    # windowing is by buffer line, which keeps the math simple.
    _scroll_offset: int = 0

    # Header count annotations, cached per Buffer — buffers are
    # immutable, so identity is a sound cache key.
    _counts_key: Buffer | None = None
    _counts: dict[int, HeaderCount] = {}

    def _header_counts(self) -> dict[int, HeaderCount]:
        assert self.buffer is not None
        if self.buffer is not self._counts_key:
            self._counts = header_counts(self.buffer)
            self._counts_key = self.buffer
        return self._counts

    def _visible_range(self) -> tuple[int, int]:
        """The [start, end) buffer-line window for the current viewport.

        An unmounted widget (or one taller than its content) renders
        everything, preserving offscreen render() behavior in tests.
        """
        assert self.buffer is not None
        total = self.buffer.line_count()
        viewport = self.size.height
        if viewport <= 0 or total <= viewport:
            self._scroll_offset = 0
            return 0, total
        row = min(self.cursor.row, total - 1)
        self._scroll_offset = compute_scroll_offset(
            row, self._scroll_offset, total, viewport, _SCROLLOFF
        )
        return self._scroll_offset, min(self._scroll_offset + viewport, total)

    def render(self) -> Text:
        if self.buffer is None:
            return Text("No deck loaded", style="dim")

        start, end = self._visible_range()
        counts = self._header_counts()
        output = Text()
        for i in range(start, end):
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
                line_error=self.line_errors.get(i),
                header_count=counts.get(i),
                plan_delta=self.plan_deltas.get(i),
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

    def watch_line_errors(
        self,
        _old: dict[int, ValidationError],
        _new: dict[int, ValidationError],
    ) -> None:
        self.refresh()

    def watch_plan_deltas(self, _old: dict[int, int], _new: dict[int, int]) -> None:
        self.refresh()

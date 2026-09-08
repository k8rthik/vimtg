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
from vimtg.tui.widgets.scrolling import compute_block_scroll_offset

# Rows of context kept above/below the cursor block (vim's scrolloff),
# and the blank rows the view may scroll past the last line so a card
# at the end of the deck still shows its expansion with that context.
_SCROLLOFF = 3
_BOTTOM_PAD = 3


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

    # Buffer-line scroll offset; follows the cursor. The window is
    # sized in rendered rows, so the cursor row's inline expansion
    # counts toward what must stay on screen.
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

    def _visible_range(self, cursor_row: int, block_height: int) -> tuple[int, int]:
        """The [start, end) buffer-line window for the current viewport.

        `block_height` is how many rows the cursor line renders (its own
        row plus expansion). An unmounted widget (or one taller than
        its content) renders everything, preserving offscreen render()
        behavior in tests.
        """
        assert self.buffer is not None
        total = self.buffer.line_count()
        viewport = self.size.height
        self._scroll_offset = compute_block_scroll_offset(
            cursor_row, block_height, self._scroll_offset, total, viewport,
            _SCROLLOFF, _BOTTOM_PAD,
        )
        if viewport <= 0:
            return 0, total
        rows_after_cursor = max(1, viewport - (block_height - 1))
        return self._scroll_offset, min(self._scroll_offset + rows_after_cursor, total)

    def _render_buffer_line(self, i: int, counts: dict[int, HeaderCount]) -> list[Text]:
        assert self.buffer is not None
        dimmed = (
            self.tag_filter is not None
            and self.buffer.is_card_line(i)
            and not matches_filter(self.buffer.tags_at(i), self.tag_filter)
        )
        return render_line(
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

    def render(self) -> Text:
        if self.buffer is None:
            return Text("No deck loaded", style="dim")
        total = self.buffer.line_count()
        if total == 0:
            return Text()

        counts = self._header_counts()
        # Render the cursor line first: its height (row + expansion)
        # decides how far the window must scroll to keep it whole.
        cursor_row = min(self.cursor.row, total - 1)
        cursor_lines = self._render_buffer_line(cursor_row, counts)
        start, end = self._visible_range(cursor_row, len(cursor_lines))

        output = Text()
        for i in range(start, end):
            lines = cursor_lines if i == cursor_row else self._render_buffer_line(i, counts)
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

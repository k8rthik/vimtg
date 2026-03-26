"""SearchResults widget — floating overlay for insert-mode card search."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.card import Card
from vimtg.tui.deck_renderer import format_mana
from vimtg.tui.theme import COLORS

_MAX_VISIBLE = 10
_SCROLLOFF = 2
_SELECTED_STYLE = f"on {COLORS['cursor_bg']}"
_DIM = f"dim {COLORS['comment']}"


def _compute_scroll_offset(
    selected: int,
    current_offset: int,
    total: int,
    viewport: int = _MAX_VISIBLE,
    scrolloff: int = _SCROLLOFF,
) -> int:
    """Compute scroll offset to keep selected within viewport with scrolloff.

    Pure function — returns a new offset value without mutation.
    """
    if total <= viewport:
        return 0

    max_offset = total - viewport
    offset = current_offset

    # Scrolling down: selection too close to bottom of viewport
    if selected > offset + viewport - 1 - scrolloff:
        offset = selected - viewport + 1 + scrolloff

    # Scrolling up: selection too close to top of viewport
    if selected < offset + scrolloff:
        offset = selected - scrolloff

    return max(0, min(offset, max_offset))


class SearchResults(Static):
    """Popup showing fuzzy card search results with inline preview."""

    results: reactive[list[Card]] = reactive(list)
    selected: reactive[int] = reactive(0)
    price_source: reactive[str] = reactive("usd")
    currency_symbol: reactive[str] = reactive("$")
    show_prices: reactive[bool] = reactive(True)
    _scroll_offset: int = 0

    def watch_results(self, _results: list[Card]) -> None:
        """Reset scroll position when results change."""
        self._scroll_offset = 0

    def render(self) -> Text:
        if not self.results:
            return Text("")

        t = Text()
        count = len(self.results)
        header = f" {count} match{'es' if count != 1 else ''}  "
        nav = "Tab/Ctrl-J next  Ctrl-K prev  Enter confirm  Esc cancel"
        t.append(f" {header}", style=f"bold {COLORS['mana_blue']}")
        t.append(f"{nav}\n", style=_DIM)

        end = min(self._scroll_offset + _MAX_VISIBLE, count)
        visible = self.results[self._scroll_offset:end]

        if self._scroll_offset > 0:
            t.append("   ... more above\n", style=_DIM)

        for i, card in enumerate(visible):
            absolute_idx = self._scroll_offset + i
            is_sel = absolute_idx == self.selected
            line = Text()

            # Selection indicator
            line.append(" > " if is_sel else "   ")

            # Card name
            line.append(f"{card.name:<28}", style="bold" if is_sel else "")

            # Mana cost
            line.append(format_mana(card.mana_cost))

            # Type
            type_short = card.type_line.split("\u2014")[0].strip()[:18]
            line.append(f"  {type_short:<18}", style="dim")

            # Price
            if self.show_prices:
                price = card.prices.get(self.price_source)
                if price is not None:
                    line.append(f"  {self.currency_symbol}{price:.2f}", style="dim")

            if is_sel:
                line.stylize(_SELECTED_STYLE)

            t.append(line)
            t.append("\n")

            # Show oracle text for selected card
            if is_sel and card.oracle_text:
                oracle_preview = card.oracle_text.replace("\n", " ")
                if len(oracle_preview) > 72:
                    oracle_preview = oracle_preview[:69] + "..."
                t.append(f"     {oracle_preview}\n", style=_DIM)

        if end < count:
            t.append(f"   ... {count - end} more below\n", style=_DIM)

        return t

    def select_next(self) -> None:
        if self.results:
            new_selected = min(self.selected + 1, len(self.results) - 1)
            self._scroll_offset = _compute_scroll_offset(
                new_selected, self._scroll_offset, len(self.results),
            )
            self.selected = new_selected

    def select_prev(self) -> None:
        new_selected = max(self.selected - 1, 0)
        self._scroll_offset = _compute_scroll_offset(
            new_selected, self._scroll_offset, len(self.results),
        )
        self.selected = new_selected

    def get_selected(self) -> Card | None:
        if 0 <= self.selected < len(self.results):
            return self.results[self.selected]
        return None

"""SearchResults widget — floating overlay for insert-mode card search."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.card import Card
from vimtg.tui.deck_renderer import format_mana
from vimtg.tui.theme import COLORS

_MAX_VISIBLE = 10
_SELECTED_STYLE = f"on {COLORS['cursor_bg']}"
_DIM = f"dim {COLORS['comment']}"


class SearchResults(Static):
    """Popup showing fuzzy card search results with inline preview."""

    results: reactive[list[Card]] = reactive(list)
    selected: reactive[int] = reactive(0)
    visible: reactive[bool] = reactive(False)
    price_source: reactive[str] = reactive("usd")
    currency_symbol: reactive[str] = reactive("$")
    show_prices: reactive[bool] = reactive(True)

    def render(self) -> Text:
        if not self.visible or not self.results:
            return Text("")

        t = Text()
        count = len(self.results)
        header = f" {count} match{'es' if count != 1 else ''}  "
        nav = "Tab/Ctrl-N next  Ctrl-P prev  Enter confirm  Esc cancel"
        t.append(f" {header}", style=f"bold {COLORS['mana_blue']}")
        t.append(f"{nav}\n", style=_DIM)

        visible = self.results[:_MAX_VISIBLE]
        for i, card in enumerate(visible):
            is_sel = i == self.selected
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

        if count > _MAX_VISIBLE:
            t.append(f"   ... and {count - _MAX_VISIBLE} more\n", style=_DIM)

        return t

    def select_next(self) -> None:
        if self.results:
            self.selected = min(self.selected + 1, len(self.results) - 1)

    def select_prev(self) -> None:
        self.selected = max(self.selected - 1, 0)

    def get_selected(self) -> Card | None:
        if 0 <= self.selected < len(self.results):
            return self.results[self.selected]
        return None

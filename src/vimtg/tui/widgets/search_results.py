"""SearchResults widget — floating overlay for insert-mode card search."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.card import Card
from vimtg.tui.deck_renderer import format_mana
from vimtg.tui.theme import COLORS

_MAX_VISIBLE = 15


class SearchResults(Static):
    """Popup showing fuzzy card search results during insert mode."""

    results: reactive[list[Card]] = reactive(list)
    selected: reactive[int] = reactive(0)
    visible: reactive[bool] = reactive(False)

    def render(self) -> Text:
        if not self.visible or not self.results:
            return Text("")

        t = Text()
        t.append(
            "\u250c\u2500 Search Results "
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
            "\u2500\u2500\u2500\u2500\u2500\u2510\n",
            style="dim",
        )

        visible = self.results[:_MAX_VISIBLE]
        for i, card in enumerate(visible):
            prefix = "\u2502>" if i == self.selected else "\u2502 "
            style = f"on {COLORS['cursor_bg']}" if i == self.selected else ""
            line = Text(f"{prefix} {card.name:<26}", style=style)
            line.append(format_mana(card.mana_cost))
            type_short = card.type_line.split("\u2014")[0].strip()[:16]
            line.append(f"  {type_short}", style="dim")
            t.append(line)
            t.append("\n")

        t.append(
            "\u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
            "\u2500\u2500\u2500\u2518\n",
            style="dim",
        )
        return t

    def select_next(self) -> None:
        """Move selection down, clamped to list bounds."""
        if self.results:
            self.selected = min(self.selected + 1, len(self.results) - 1)

    def select_prev(self) -> None:
        """Move selection up, clamped to 0."""
        self.selected = max(self.selected - 1, 0)

    def get_selected(self) -> Card | None:
        """Return the currently highlighted card, or None."""
        if 0 <= self.selected < len(self.results):
            return self.results[self.selected]
        return None

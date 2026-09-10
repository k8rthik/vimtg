"""EdhrecPanel widget — EDHREC recommendations with per-card-type tabs.

Companion-pane sibling of DeckView: a tab bar (one tab per card type),
a scrolling recommendation list, and a checkmark on cards the deck
already runs. All data arrives via reactives; fetching happens in
MainScreen's worker.
"""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.services.edhrec import EdhrecCard, EdhrecPage
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scrolling import (
    WHEEL_LINES,
    compute_scroll_offset,
    marker_above,
    marker_below,
)

_SCROLLOFF = 2
# Header + tab bar + hint line + "more" indicators
_CHROME_ROWS = 5
_SELECTED_STYLE = f"on {COLORS['cursor_bg']}"
_DIM = f"dim {COLORS['comment']}"


class EdhrecPanel(Static):
    """EDHREC recommendation list for the deck's commander(s)."""

    page: reactive[EdhrecPage | None] = reactive(None)
    status: reactive[str] = reactive("")  # loading / error text
    status_error: reactive[bool] = reactive(False)
    active_tab: reactive[int] = reactive(0)
    selected: reactive[int] = reactive(0)
    focused_panel: reactive[bool] = reactive(False)
    deck_names: reactive[frozenset[str]] = reactive(frozenset)  # lowercase

    _scroll_offset: int = 0

    # ── Navigation API (driven by MainScreen key handling) ───────

    def _cards(self) -> tuple[EdhrecCard, ...]:
        if self.page is None or not self.page.tabs:
            return ()
        return self.page.tabs[self.active_tab].cards

    def next_tab(self) -> None:
        if self.page and self.page.tabs:
            self._set_tab((self.active_tab + 1) % len(self.page.tabs))

    def prev_tab(self) -> None:
        if self.page and self.page.tabs:
            self._set_tab((self.active_tab - 1) % len(self.page.tabs))

    def set_tab_by_label(self, label: str) -> None:
        """Activate the tab whose label matches (no-op when absent)."""
        if not self.page or not label:
            return
        for i, tab in enumerate(self.page.tabs):
            if tab.label.lower() == label.lower():
                self._set_tab(i)
                return

    def _set_tab(self, index: int) -> None:
        self.active_tab = index
        self.selected = 0
        self._scroll_offset = 0

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        for _ in range(WHEEL_LINES):
            self.select_next()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        for _ in range(WHEEL_LINES):
            self.select_prev()

    def select_next(self) -> None:
        self.select_by(1)

    def select_prev(self) -> None:
        self.select_by(-1)

    def select_by(self, delta: int) -> None:
        cards = self._cards()
        if cards:
            self.selected = max(0, min(self.selected + delta, len(cards) - 1))
        else:
            self.selected = 0

    def select_first(self) -> None:
        self.select_by(-len(self._cards()))

    def select_last(self) -> None:
        self.select_by(len(self._cards()))

    def viewport_rows(self) -> int:
        return self._viewport()

    def get_selected(self) -> EdhrecCard | None:
        cards = self._cards()
        if 0 <= self.selected < len(cards):
            return cards[self.selected]
        return None

    # ── Rendering ────────────────────────────────────────────────

    def render(self) -> Text:
        t = Text()
        self._render_header(t)
        if self.page is None:
            style = f"bold {COLORS['error']}" if self.status_error else "dim"
            t.append(f" {self.status or 'No recommendations loaded'}\n", style=style)
            return t
        self._render_tab_bar(t)
        self._render_cards(t)
        return t

    def _render_header(self, t: Text) -> None:
        accent = COLORS["focus"] if self.focused_panel else COLORS["comment"]
        title = " EDHREC"
        if self.page is not None and self.page.commander:
            title += f" — {self.page.commander}"
        t.append(title + "\n", style=f"bold {accent}")
        width = max(20, self.size.width or 60)
        t.append("─" * min(width, 80) + "\n", style=f"dim {accent}")

    def _render_tab_bar(self, t: Text) -> None:
        assert self.page is not None
        t.append(" ")
        for i, tab in enumerate(self.page.tabs):
            if i == self.active_tab:
                t.append(f" {tab.label} ", style=f"bold reverse {COLORS['mana_blue']}")
            else:
                t.append(f" {tab.label} ", style="dim")
        t.append("\n")

    def _viewport(self) -> int:
        height = self.size.height
        if height <= 0:
            return 15
        return max(3, height - _CHROME_ROWS)

    def _render_cards(self, t: Text) -> None:
        cards = self._cards()
        if not cards:
            t.append(" (no cards in this tab)\n", style="dim")
            return

        viewport = self._viewport()
        self._scroll_offset = compute_scroll_offset(
            min(self.selected, len(cards) - 1),
            self._scroll_offset, len(cards), viewport, _SCROLLOFF,
        )
        start = self._scroll_offset
        end = min(start + viewport, len(cards))

        if start > 0:
            t.append(marker_above() + "\n", style=_DIM)
        for i in range(start, end):
            t.append(self._card_row(cards[i], i))
            t.append("\n")
        if end < len(cards):
            t.append(marker_below(len(cards) - end) + "\n", style=_DIM)
        if self.focused_panel:
            t.append(
                " j/k select  h/l tabs  Enter add card  Esc back\n", style=_DIM
            )

    def _card_row(self, card: EdhrecCard, index: int) -> Text:
        is_sel = index == self.selected
        in_deck = card.name.lower() in self.deck_names
        line = Text()
        line.append(" > " if is_sel else "   ")
        mark = "✓ " if in_deck else "  "
        line.append(mark, style=COLORS["success"])
        name_style = "bold" if is_sel else ""
        if in_deck:
            name_style = f"dim {name_style}".strip()
        line.append(f"{card.name:<32}", style=name_style)
        line.append(f"  {card.inclusion_pct:3.0f}% of decks", style="dim")
        if card.synergy:
            sign = "+" if card.synergy >= 0 else ""
            line.append(
                f"  {sign}{card.synergy * 100:.0f}% synergy",
                style=f"dim {COLORS['category']}",
            )
        if is_sel:
            line.stylize(_SELECTED_STYLE)
        return line

    # ── Reactive watchers ────────────────────────────────────────

    def watch_page(self, _old: EdhrecPage | None, _new: EdhrecPage | None) -> None:
        self.active_tab = 0
        self.selected = 0
        self._scroll_offset = 0
        self.refresh()

    def watch_status(self, _old: str, _new: str) -> None:
        self.refresh()

    def watch_active_tab(self, _old: int, _new: int) -> None:
        self.refresh()

    def watch_selected(self, _old: int, _new: int) -> None:
        self.refresh()

    def watch_focused_panel(self, _old: bool, _new: bool) -> None:
        self.refresh()

    def watch_deck_names(
        self, _old: frozenset[str], _new: frozenset[str]
    ) -> None:
        self.refresh()

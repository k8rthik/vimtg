"""AnalyticsPanel widget — live deck analytics in the split pane.

Companion-pane sibling of DeckView: mana curve, counts per
type/zone/category, mana-base check, and draw odds that follow the
cursor's card. All data arrives via reactives; MainScreen recomputes
AnalyticsData when the buffer changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.analytics import (
    DeckStats,
    ManaBaseCheck,
    category_counts,
    compute_mana_base,
    compute_stats,
    zone_counts,
)
from vimtg.domain.card import Card, Color
from vimtg.domain.deck import Deck, DeckSection
from vimtg.domain.probabilities import (
    OPENING_HAND_SIZE,
    draws_by_turn,
    prob_at_least,
)
from vimtg.tui.theme import COLORS

_CURVE_BAR_WIDTH = 24
_DIM = f"dim {COLORS['comment']}"
_ZONE_LABELS: dict[DeckSection, str] = {
    DeckSection.COMMANDER: "cmd",
    DeckSection.COMPANION: "cmp",
    DeckSection.MAIN: "main",
    DeckSection.SIDEBOARD: "side",
    DeckSection.MAYBEBOARD: "maybe",
}
_PIP_STYLES: dict[Color, str] = {
    Color.WHITE: COLORS["mana_white"],
    Color.BLUE: COLORS["mana_blue"],
    Color.BLACK: COLORS["mana_black"],
    Color.RED: COLORS["mana_red"],
    Color.GREEN: COLORS["mana_green"],
}


@dataclass(frozen=True)
class AnalyticsData:
    """Everything the panel renders, computed from one buffer state."""

    stats: DeckStats
    zones: tuple[tuple[str, int], ...]  # (label, count), empty zones dropped
    categories: tuple[tuple[str, int], ...]  # only when the deck uses any
    mana_base: ManaBaseCheck
    deck_size: int  # mainboard cards, the draw-odds population


def build_analytics_data(
    deck: Deck, resolved_cards: dict[str, Card], price_source: str = "usd"
) -> AnalyticsData:
    """Compute the full analytics bundle for one deck state."""
    stats = compute_stats(deck, resolved_cards, price_source)
    zones = tuple(
        (_ZONE_LABELS[section], count)
        for section, count in zone_counts(deck).items()
        if count > 0
    )
    by_category = category_counts(deck)
    categories: tuple[tuple[str, int], ...] = ()
    if any(name for name in by_category):
        categories = tuple(
            (name or "(none)", by_category[name])
            for name in sorted(by_category, key=lambda n: (n == "", n))
        )
    return AnalyticsData(
        stats=stats,
        zones=zones,
        categories=categories,
        mana_base=compute_mana_base(deck, resolved_cards),
        deck_size=stats.mainboard_count,
    )


class AnalyticsPanel(Static):
    """Live analytics for the deck being edited."""

    data: reactive[AnalyticsData | None] = reactive(None)
    cursor_card: reactive[tuple[str, int] | None] = reactive(None)
    focused_panel: reactive[bool] = reactive(False)
    # Name of the sideboard plan the data was boarded with ('' = pre-board)
    plan_name: reactive[str] = reactive("")

    _scroll_offset: int = 0

    def scroll_line_down(self) -> None:
        self._scroll_offset += 1
        self.refresh()

    def scroll_line_up(self) -> None:
        self._scroll_offset = max(0, self._scroll_offset - 1)
        self.refresh()

    # ── Rendering ────────────────────────────────────────────────

    def render(self) -> Text:
        t = Text()
        self._render_header(t)
        if self.data is None:
            t.append(" No deck data (is the card database synced?)\n", style="dim")
            return t
        lines = self._body_lines(self.data)
        viewport = self._viewport()
        self._scroll_offset = max(
            0, min(self._scroll_offset, len(lines) - viewport)
        )
        start = self._scroll_offset
        end = min(start + viewport, len(lines))
        if start > 0:
            t.append("   ... more above\n", style=_DIM)
        for line in lines[start:end]:
            t.append(line)
            t.append("\n")
        if end < len(lines):
            t.append(f"   ... {len(lines) - end} more below\n", style=_DIM)
        if self.focused_panel:
            t.append(" j/k scroll  Esc back\n", style=_DIM)
        return t

    def _render_header(self, t: Text) -> None:
        accent = COLORS["focus"] if self.focused_panel else COLORS["comment"]
        t.append(" ANALYTICS", style=f"bold {accent}")
        if self.plan_name:
            t.append(f" vs {self.plan_name}", style=f"bold {COLORS['sideboard']}")
            t.append(" (post-board)", style="dim")
        if self.data is not None:
            s = self.data.stats
            t.append(
                f" — {s.mainboard_count} main · avg cmc {s.average_cmc:.2f}",
                style="dim",
            )
        t.append("\n")
        width = max(20, self.size.width or 60)
        t.append("─" * min(width, 80) + "\n", style=f"dim {accent}")

    def _viewport(self) -> int:
        height = self.size.height
        if height <= 0:
            return 40
        return max(3, height - 4)  # header + rule + hint + overflow rows

    def _body_lines(self, data: AnalyticsData) -> list[Text]:
        lines: list[Text] = []
        self._curve_lines(lines, data)
        self._type_lines(lines, data)
        self._zone_lines(lines, data)
        self._category_lines(lines, data)
        self._mana_base_lines(lines, data)
        self._draw_lines(lines, data)
        return lines

    def _heading(self, lines: list[Text], label: str) -> None:
        if lines:
            lines.append(Text())
        lines.append(Text(f" {label}", style=f"bold {COLORS['category']}"))

    def _curve_lines(self, lines: list[Text], data: AnalyticsData) -> None:
        curve = data.stats.mana_curve
        self._heading(lines, "CURVE")
        peak = curve.max_count()
        for cmc in sorted(curve.buckets):
            count = curve.buckets[cmc]
            if count == 0:
                continue
            bar = "█" * max(1, round(count / peak * _CURVE_BAR_WIDTH))
            label = "7+" if cmc >= 7 else str(cmc)
            row = Text(f"  {label:>2} ")
            row.append(bar, style=COLORS["mana_blue"])
            row.append(f" {count}", style="dim")
            lines.append(row)
        if curve.total() == 0:
            lines.append(Text("  (no resolved nonland cards)", style="dim"))

    def _type_lines(self, lines: list[Text], data: AnalyticsData) -> None:
        counts = data.stats.type_breakdown.counts
        if not counts:
            return
        self._heading(lines, "TYPES")
        for tname in sorted(counts, key=counts.get, reverse=True):  # type: ignore[arg-type]
            lines.append(Text(f"  {tname:<13} {counts[tname]}"))

    def _zone_lines(self, lines: list[Text], data: AnalyticsData) -> None:
        self._heading(lines, "ZONES")
        row = Text("  ")
        row.append(" · ".join(f"{label} {n}" for label, n in data.zones))
        lines.append(row)

    def _category_lines(self, lines: list[Text], data: AnalyticsData) -> None:
        if not data.categories:
            return
        self._heading(lines, "CATEGORIES")
        for name, count in data.categories:
            style = "dim" if name == "(none)" else ""
            lines.append(Text(f"  {name:<13} {count}", style=style))

    def _mana_base_lines(self, lines: list[Text], data: AnalyticsData) -> None:
        check = data.mana_base
        self._heading(lines, f"MANA BASE ({check.total_lands} lands)")
        if not check.requirements:
            lines.append(Text("  (no colored pips resolved)", style="dim"))
            return
        for req in check.requirements:
            row = Text("  ")
            row.append(req.color.value, style=f"bold {_PIP_STYLES[req.color]}")
            row.append(f"  {req.pips:>3} pips   ")
            row.append(f"{req.sources}/{req.needed} sources ")
            if req.satisfied:
                row.append("✓", style=COLORS["success"])
            else:
                row.append(
                    f"✗ need {req.needed - req.sources} more",
                    style=f"bold {COLORS['error']}",
                )
            lines.append(row)

    def _draw_lines(self, lines: list[Text], data: AnalyticsData) -> None:
        self._heading(lines, "DRAWS")
        deck_size = data.deck_size
        lands = data.stats.land_count
        if deck_size > 0 and lands > 0:
            p = prob_at_least(2, lands, deck_size, OPENING_HAND_SIZE)
            lines.append(Text(f"  ≥2 lands in opener   {p:>4.0%}"))
            p3 = prob_at_least(3, lands, deck_size, draws_by_turn(3))
            lines.append(Text(f"  3 land drops by t3   {p3:>4.0%}"))
        if self.cursor_card is not None:
            name, copies = self.cursor_card
            opener = prob_at_least(1, copies, deck_size, OPENING_HAND_SIZE)
            by_t3 = prob_at_least(1, copies, deck_size, draws_by_turn(3))
            row = Text(f"  {name[:20]:<20} ", style="bold")
            row.append(
                f"opener {opener:>4.0%} · by t3 {by_t3:>4.0%}", style=""
            )
            lines.append(row)

    # ── Reactive watchers ────────────────────────────────────────

    def watch_data(
        self, _old: AnalyticsData | None, _new: AnalyticsData | None
    ) -> None:
        self.refresh()

    def watch_cursor_card(
        self, _old: tuple[str, int] | None, _new: tuple[str, int] | None
    ) -> None:
        self.refresh()

    def watch_focused_panel(self, _old: bool, _new: bool) -> None:
        self.refresh()

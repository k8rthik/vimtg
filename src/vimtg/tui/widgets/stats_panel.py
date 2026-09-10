"""Stats panel — renders stats comparison between two deck states."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive

from vimtg.domain.deck_diff import StatsDelta
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.scroll_panel import ScrollablePanel


def _delta_str(old: float | int, new: float | int, fmt: str = ".0f") -> Text:
    """Format a delta value with color: green for positive, red for negative."""
    t = Text()
    diff = new - old
    if isinstance(old, float) or isinstance(new, float):
        t.append(f"{old:{fmt}} → {new:{fmt}}", style="")
    else:
        t.append(f"{old} → {new}", style="")

    if diff > 0:
        t.append(f"  (+{diff:{fmt}})", style=f"{COLORS['mana_green']}")
    elif diff < 0:
        t.append(f"  ({diff:{fmt}})", style=f"{COLORS['mana_red']}")
    return t


def _price_delta_str(
    old_price: float | None, new_price: float | None, symbol: str = "$"
) -> Text:
    """Format price delta with the configured currency symbol."""
    t = Text()
    if old_price is None and new_price is None:
        t.append("N/A", style="dim")
        return t
    old_p = old_price or 0.0
    new_p = new_price or 0.0
    t.append(f"{symbol}{old_p:.2f} → {symbol}{new_p:.2f}", style="")
    diff = new_p - old_p
    if diff > 0:
        t.append(f"  (+{symbol}{diff:.2f})", style=f"{COLORS['mana_green']}")
    elif diff < 0:
        t.append(f"  (-{symbol}{abs(diff):.2f})", style=f"{COLORS['mana_red']}")
    return t


class StatsPanel(ScrollablePanel):
    """Renders stats comparison between two deck states."""

    title = "Stats"
    DEFAULT_PLACEHOLDER = "Select a snapshot to view stats"

    placeholder: reactive[str] = reactive(DEFAULT_PLACEHOLDER)
    stats_delta: reactive[StatsDelta | None] = reactive(None, recompose=False)
    currency: reactive[str] = reactive("$")

    def watch_stats_delta(self) -> None:
        self.scroll_to_top()

    def body_lines(self) -> list[Text]:
        if self.stats_delta is None:
            return [Text(f"  {self.placeholder}", style="dim")]
        sd = self.stats_delta
        lines: list[Text] = []

        cards = Text("  Cards:   ", style="dim")
        cards.append_text(_delta_str(sd.old_total, sd.new_total))
        lines.append(cards)

        cmc = Text("  Avg CMC: ", style="dim")
        cmc.append_text(_delta_str(sd.old_avg_cmc, sd.new_avg_cmc, ".2f"))
        lines.append(cmc)

        price = Text("  Price:   ", style="dim")
        price.append_text(_price_delta_str(sd.old_price, sd.new_price, self.currency))
        lines.append(price)

        if sd.curve_delta:
            lines.append(Text(""))
            lines.append(Text("  Curve Δ:", style=f"dim {COLORS['comment']}"))
            for bucket in sorted(sd.curve_delta.keys()):
                delta = sd.curve_delta[bucket]
                label = "7+" if bucket >= 7 else str(bucket)
                color = COLORS["mana_green"] if delta > 0 else COLORS["mana_red"]
                sign = "+" if delta > 0 else ""
                row = Text(f"  {label}: ", style="dim")
                row.append(f"{sign}{delta}", style=f"{color}")
                lines.append(row)
        return lines

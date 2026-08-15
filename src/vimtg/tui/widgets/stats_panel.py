"""Stats panel — renders stats comparison between two deck states."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from vimtg.domain.deck_diff import StatsDelta
from vimtg.tui.theme import COLORS


def _delta_str(old: float | int, new: float | int, fmt: str = ".0f") -> Text:
    """Format a delta value with color: green for positive, red for negative."""
    t = Text()
    diff = new - old
    if isinstance(old, float) or isinstance(new, float):
        t.append(f"{old:{fmt}} \u2192 {new:{fmt}}", style="")
    else:
        t.append(f"{old} \u2192 {new}", style="")

    if diff > 0:
        t.append(f"  (+{diff:{fmt}})", style=f"{COLORS['mana_green']}")
    elif diff < 0:
        t.append(f"  ({diff:{fmt}})", style=f"{COLORS['mana_red']}")
    return t


def _price_delta_str(
    old_price: float | None, new_price: float | None
) -> Text:
    """Format price delta with currency symbol."""
    t = Text()
    if old_price is None and new_price is None:
        t.append("N/A", style="dim")
        return t
    old_p = old_price or 0.0
    new_p = new_price or 0.0
    t.append(f"${old_p:.2f} \u2192 ${new_p:.2f}", style="")
    diff = new_p - old_p
    if diff > 0:
        t.append(f"  (+${diff:.2f})", style=f"{COLORS['mana_green']}")
    elif diff < 0:
        t.append(f"  (-${abs(diff):.2f})", style=f"{COLORS['mana_red']}")
    return t


class StatsPanel(Static):
    """Renders stats comparison between two deck states."""

    stats_delta: reactive[StatsDelta | None] = reactive(None, recompose=False)
    focused_panel: reactive[bool] = reactive(False)

    def render(self) -> Text:
        t = Text()
        border_color = COLORS["mana_red"] if self.focused_panel else COLORS["comment"]
        t.append(" Stats", style=f"bold {border_color}")
        t.append("\n")
        t.append(f" {'─' * 40}\n", style=f"dim {COLORS['comment']}")

        if self.stats_delta is None:
            t.append("  Select a snapshot to view stats\n", style="dim")
            return t

        sd = self.stats_delta

        # Cards
        t.append("  Cards:   ", style="dim")
        t.append_text(_delta_str(sd.old_total, sd.new_total))
        t.append("\n")

        # Avg CMC
        t.append("  Avg CMC: ", style="dim")
        t.append_text(_delta_str(sd.old_avg_cmc, sd.new_avg_cmc, ".2f"))
        t.append("\n")

        # Price
        t.append("  Price:   ", style="dim")
        t.append_text(_price_delta_str(sd.old_price, sd.new_price))
        t.append("\n")

        # Mana curve delta
        if sd.curve_delta:
            t.append("\n")
            t.append("  Curve \u0394:\n", style=f"dim {COLORS['comment']}")
            for bucket in sorted(sd.curve_delta.keys()):
                delta = sd.curve_delta[bucket]
                label = "7+" if bucket >= 7 else str(bucket)
                color = COLORS["mana_green"] if delta > 0 else COLORS["mana_red"]
                sign = "+" if delta > 0 else ""
                t.append(f"  {label}: ", style="dim")
                t.append(f"{sign}{delta}", style=f"{color}")
                t.append("\n")

        return t

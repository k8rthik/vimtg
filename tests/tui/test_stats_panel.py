"""Tests for StatsPanel — delta formatting, curve display, color coding."""

from __future__ import annotations

from vimtg.domain.deck_diff import StatsDelta
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.stats_panel import (
    StatsPanel,
    _delta_str,
    _price_delta_str,
)


def _styles_at(label: str, text) -> str:
    start = text.plain.index(label)
    styles: list[str] = []
    for span in text.spans:
        if span.start <= start < span.end:
            styles.append(str(span.style))
    return " ".join(styles)


# ── _delta_str ─────────────────────────────────────────────────────


class TestDeltaStr:
    def test_positive_int_delta_uses_plus_and_green(self) -> None:
        text = _delta_str(40, 60)
        assert "40 → 60" in text.plain
        assert "(+20)" in text.plain
        assert COLORS["mana_green"] in _styles_at("(+20)", text)

    def test_negative_int_delta_uses_minus_and_red(self) -> None:
        text = _delta_str(60, 40)
        assert "60 → 40" in text.plain
        assert "(-20)" in text.plain
        assert COLORS["mana_red"] in _styles_at("(-20)", text)

    def test_zero_delta_has_no_sign_segment(self) -> None:
        text = _delta_str(40, 40)
        # 40 → 40 should be present, but no parenthesized delta
        assert "40 → 40" in text.plain
        assert "(+0)" not in text.plain
        assert "(-0)" not in text.plain

    def test_float_format_for_avg_cmc(self) -> None:
        text = _delta_str(2.5, 3.0, ".2f")
        assert "2.50 → 3.00" in text.plain
        assert "(+0.50)" in text.plain


# ── _price_delta_str ───────────────────────────────────────────────


class TestPriceDeltaStr:
    def test_both_none_shows_na(self) -> None:
        text = _price_delta_str(None, None)
        assert text.plain == "N/A"

    def test_old_none_treated_as_zero(self) -> None:
        text = _price_delta_str(None, 10.0)
        assert "$0.00 → $10.00" in text.plain
        assert "(+$10.00)" in text.plain

    def test_price_decrease_uses_red(self) -> None:
        text = _price_delta_str(100.0, 75.0)
        assert "$100.00 → $75.00" in text.plain
        assert "(-$25.00)" in text.plain
        assert COLORS["mana_red"] in _styles_at("(-$25.00)", text)

    def test_price_increase_uses_green(self) -> None:
        text = _price_delta_str(50.0, 75.0)
        assert "(+$25.00)" in text.plain
        assert COLORS["mana_green"] in _styles_at("(+$25.00)", text)

    def test_no_change_no_paren_segment(self) -> None:
        text = _price_delta_str(50.0, 50.0)
        assert "$50.00 → $50.00" in text.plain
        assert "(+" not in text.plain
        assert "(-" not in text.plain


# ── StatsPanel.render ──────────────────────────────────────────────


def _stats_delta(**overrides: object) -> StatsDelta:
    defaults = {
        "old_total": 60,
        "new_total": 60,
        "old_avg_cmc": 2.5,
        "new_avg_cmc": 2.5,
        "old_price": 100.0,
        "new_price": 100.0,
        "curve_delta": {},
    }
    defaults.update(overrides)
    return StatsDelta(**defaults)  # type: ignore[arg-type]


class TestStatsPanelEmpty:
    def test_no_delta_shows_placeholder(self) -> None:
        p = StatsPanel()
        text = p.render()
        assert "Select a snapshot" in text.plain


class TestStatsPanelRender:
    def test_renders_cards_avg_cmc_price(self) -> None:
        p = StatsPanel()
        p.stats_delta = _stats_delta(
            old_total=40, new_total=60,
            old_avg_cmc=2.5, new_avg_cmc=2.8,
            old_price=10.0, new_price=20.0,
        )
        plain = p.render().plain
        assert "Cards:" in plain
        assert "40 → 60" in plain
        assert "Avg CMC:" in plain
        assert "2.50 → 2.80" in plain
        assert "Price:" in plain
        assert "$10.00 → $20.00" in plain

    def test_curve_delta_section_only_when_nonempty(self) -> None:
        p = StatsPanel()
        p.stats_delta = _stats_delta(curve_delta={})
        assert "Curve" not in p.render().plain

    def test_curve_delta_renders_each_bucket(self) -> None:
        p = StatsPanel()
        p.stats_delta = _stats_delta(curve_delta={0: 2, 1: -3, 7: 1})
        plain = p.render().plain
        assert "Curve" in plain
        assert "0:" in plain
        assert "+2" in plain
        assert "1:" in plain
        assert "-3" in plain
        # 7+ bucket label
        assert "7+:" in plain
        assert "+1" in plain

    def test_curve_positive_delta_uses_green(self) -> None:
        p = StatsPanel()
        p.stats_delta = _stats_delta(curve_delta={2: 4})
        text = p.render()
        assert COLORS["mana_green"] in _styles_at("+4", text)

    def test_curve_negative_delta_uses_red(self) -> None:
        p = StatsPanel()
        p.stats_delta = _stats_delta(curve_delta={2: -4})
        text = p.render()
        assert COLORS["mana_red"] in _styles_at("-4", text)


class TestStatsPanelFocus:
    def test_focused_uses_accent_border(self) -> None:
        p = StatsPanel()
        p.focused_panel = True
        text = p.render()
        assert COLORS["mana_red"] in _styles_at("Stats", text)

    def test_unfocused_uses_dim_border(self) -> None:
        p = StatsPanel()
        p.focused_panel = False
        text = p.render()
        assert COLORS["comment"] in _styles_at("Stats", text)

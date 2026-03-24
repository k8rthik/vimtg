"""Tests for config option metadata and manipulation functions."""

import pytest

from vimtg.config.settings import Settings
from vimtg.editor.config_options import (
    CONFIG_OPTIONS,
    apply_setting,
    currency_symbol_for,
    cycle_setting,
    get_option,
    get_setting_display,
    get_setting_value,
    groups,
    navigable_options,
)


class TestCurrencySymbol:
    def test_usd(self) -> None:
        assert currency_symbol_for("usd") == "$"

    def test_usd_foil(self) -> None:
        assert currency_symbol_for("usd_foil") == "$"

    def test_eur(self) -> None:
        assert currency_symbol_for("eur") == "\u20ac"

    def test_tix(self) -> None:
        assert currency_symbol_for("tix") == "tix "

    def test_unknown_defaults_dollar(self) -> None:
        assert currency_symbol_for("unknown") == "$"


class TestGetOption:
    def test_known_option(self) -> None:
        opt = get_option("price_source")
        assert opt is not None
        assert opt.option_type == "choice"

    def test_unknown_option(self) -> None:
        assert get_option("nonexistent") is None


class TestGetSettingValue:
    def test_bool_on(self) -> None:
        assert get_setting_value(Settings(), "show_prices") == "on"

    def test_bool_off(self) -> None:
        s = Settings(show_prices=False)
        assert get_setting_value(s, "show_prices") == "off"

    def test_string_value(self) -> None:
        assert get_setting_value(Settings(), "price_source") == "usd"

    def test_int_value(self) -> None:
        assert get_setting_value(Settings(), "search_limit") == "50"

    def test_empty_string(self) -> None:
        assert get_setting_value(Settings(), "default_format") == ""


class TestGetSettingDisplay:
    def test_price_source(self) -> None:
        display = get_setting_display(Settings(), "price_source")
        assert "Price Source" in display
        assert "usd" in display


class TestApplySetting:
    def test_set_choice(self) -> None:
        s = apply_setting(Settings(), "price_source", "eur")
        assert s.price_source == "eur"

    def test_set_bool_on(self) -> None:
        s = apply_setting(Settings(show_prices=False), "show_prices", "on")
        assert s.show_prices is True

    def test_set_bool_off(self) -> None:
        s = apply_setting(Settings(), "show_prices", "off")
        assert s.show_prices is False

    def test_set_int(self) -> None:
        s = apply_setting(Settings(), "search_limit", "100")
        assert s.search_limit == 100

    def test_invalid_choice(self) -> None:
        with pytest.raises(ValueError, match="must be one of"):
            apply_setting(Settings(), "price_source", "cardkingdom")

    def test_invalid_bool(self) -> None:
        with pytest.raises(ValueError, match="must be on/off"):
            apply_setting(Settings(), "show_prices", "maybe")

    def test_int_below_min(self) -> None:
        with pytest.raises(ValueError, match="minimum"):
            apply_setting(Settings(), "search_limit", "1")

    def test_int_above_max(self) -> None:
        with pytest.raises(ValueError, match="maximum"):
            apply_setting(Settings(), "search_limit", "999")

    def test_unknown_key(self) -> None:
        with pytest.raises(ValueError, match="Unknown setting"):
            apply_setting(Settings(), "nonexistent", "value")

    def test_immutability(self) -> None:
        original = Settings()
        modified = apply_setting(original, "price_source", "eur")
        assert original.price_source == "usd"
        assert modified.price_source == "eur"


class TestCycleSetting:
    def test_cycle_bool(self) -> None:
        s = cycle_setting(Settings(), "show_prices")
        assert s.show_prices is False
        s2 = cycle_setting(s, "show_prices")
        assert s2.show_prices is True

    def test_cycle_choice_forward(self) -> None:
        s = cycle_setting(Settings(), "price_source", direction=1)
        assert s.price_source == "usd_foil"

    def test_cycle_choice_backward(self) -> None:
        s = cycle_setting(Settings(), "price_source", direction=-1)
        assert s.price_source == "tix"  # wraps around

    def test_cycle_choice_wraps(self) -> None:
        s = Settings(price_source="tix")
        s = cycle_setting(s, "price_source", direction=1)
        assert s.price_source == "usd"  # wraps to beginning

    def test_cycle_int_increases(self) -> None:
        s = cycle_setting(Settings(), "search_limit", direction=1)
        assert s.search_limit == 60  # +10

    def test_cycle_int_decreases(self) -> None:
        s = cycle_setting(Settings(), "search_limit", direction=-1)
        assert s.search_limit == 40  # -10

    def test_cycle_int_clamps_min(self) -> None:
        s = Settings(search_limit=10)
        s = cycle_setting(s, "search_limit", direction=-1)
        assert s.search_limit == 10  # clamped at min

    def test_cycle_int_clamps_max(self) -> None:
        s = Settings(search_limit=500)
        s = cycle_setting(s, "search_limit", direction=1)
        assert s.search_limit == 500  # clamped at max

    def test_unknown_key_returns_same(self) -> None:
        s = Settings()
        s2 = cycle_setting(s, "nonexistent")
        assert s2 is s


class TestGroups:
    def test_groups_ordered(self) -> None:
        g = groups()
        assert "Pricing" in g
        assert "Display" in g
        assert "Editor" in g

    def test_navigable_options_complete(self) -> None:
        nav = navigable_options()
        assert len(nav) == len(CONFIG_OPTIONS)

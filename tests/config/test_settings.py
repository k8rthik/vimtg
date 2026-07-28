"""Tests for Settings dataclass, validation, and loading."""

from pathlib import Path

import pytest

from vimtg.config.settings import (
    VALID_FORMATS,
    VALID_PRICE_SOURCES,
    Settings,
    load_settings,
    validate_settings,
)


class TestSettingsDefaults:
    def test_default_values(self) -> None:
        s = Settings()
        assert s.theme == "dark"
        assert s.show_line_numbers is True
        assert s.show_which_key is True
        assert s.auto_expand is True
        assert s.price_source == "usd"
        assert s.show_prices is True
        assert s.search_limit == 50
        assert s.default_format == ""
        assert s.auto_sort is True
        assert s.confirm_quit is True

    def test_frozen(self) -> None:
        s = Settings()
        with pytest.raises(AttributeError):
            s.price_source = "eur"  # type: ignore[misc]


class TestValidation:
    def test_valid_defaults(self) -> None:
        assert validate_settings(Settings()) == []

    def test_invalid_price_source(self) -> None:
        s = Settings(price_source="cardkingdom")
        errors = validate_settings(s)
        assert any("price_source" in e for e in errors)

    def test_all_price_sources_valid(self) -> None:
        for src in VALID_PRICE_SOURCES:
            s = Settings(price_source=src)
            assert validate_settings(s) == []

    def test_search_limit_too_low(self) -> None:
        s = Settings(search_limit=0)
        errors = validate_settings(s)
        assert any("search_limit" in e for e in errors)

    def test_search_limit_too_high(self) -> None:
        s = Settings(search_limit=1000)
        errors = validate_settings(s)
        assert any("search_limit" in e for e in errors)

    def test_invalid_format(self) -> None:
        s = Settings(default_format="invented_format")
        errors = validate_settings(s)
        assert any("default_format" in e for e in errors)

    def test_all_formats_valid(self) -> None:
        for fmt in VALID_FORMATS:
            s = Settings(default_format=fmt)
            assert validate_settings(s) == []


class TestLoadSettings:
    def test_load_with_no_file_returns_defaults(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_settings with no config file returns defaults."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        from vimtg.config.settings import load_settings

        s = load_settings()
        assert s.price_source == "usd"
        assert s.show_prices is True

    def test_load_with_partial_config(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing fields fall back to defaults."""
        config_dir = tmp_path / "vimtg"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text('[editor]\nprice_source = "eur"\n')

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        from vimtg.config.settings import load_settings

        s = load_settings()
        assert s.price_source == "eur"
        assert s.show_prices is True  # default
        assert s.search_limit == 50  # default


class TestMalformedConfig:
    """A broken config.toml must never prevent the app from starting."""

    def test_corrupt_toml_falls_back_to_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = tmp_path / "vimtg"
        cfg.mkdir()
        (cfg / "config.toml").write_text("[editor\nbroken = ", encoding="utf-8")
        settings = load_settings()
        assert settings == Settings()

    def test_wrong_types_fall_back_per_field(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = tmp_path / "vimtg"
        cfg.mkdir()
        (cfg / "config.toml").write_text(
            '[editor]\nsearch_limit = "many"\nshow_prices = false\n',
            encoding="utf-8",
        )
        settings = load_settings()
        assert settings.search_limit == Settings().search_limit
        assert settings.show_prices is False

    def test_out_of_range_values_fall_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = tmp_path / "vimtg"
        cfg.mkdir()
        (cfg / "config.toml").write_text(
            '[editor]\nprice_source = "gbp"\nsearch_limit = 9999\n',
            encoding="utf-8",
        )
        settings = load_settings()
        assert settings.price_source == "usd"
        assert settings.search_limit == Settings().search_limit

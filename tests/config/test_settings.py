"""Tests for Settings dataclass, validation, and loading."""

from pathlib import Path

import pytest

from vimtg.config.settings import (
    VALID_FORMATS,
    VALID_PRICE_SOURCES,
    Settings,
    keybinding_problems,
    load_settings,
    load_settings_checked,
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


class TestLoadSettingsChecked:
    """An unparseable config falls back to defaults, but visibly."""

    def test_no_config_no_warning(self) -> None:
        from vimtg.config.settings import load_settings_checked

        assert load_settings_checked() == (Settings(), None)

    def test_corrupt_toml_reports_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from vimtg.config.settings import load_settings_checked

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = tmp_path / "vimtg"
        cfg.mkdir()
        (cfg / "config.toml").write_text("[editor\nbroken = ", encoding="utf-8")
        settings, warning = load_settings_checked()
        assert settings == Settings()
        assert warning is not None
        assert "not valid TOML" in warning

    def test_valid_config_no_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from vimtg.config.settings import load_settings_checked

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = tmp_path / "vimtg"
        cfg.mkdir()
        (cfg / "config.toml").write_text('[editor]\nprice_source = "eur"\n', encoding="utf-8")
        settings, warning = load_settings_checked()
        assert settings.price_source == "eur"
        assert warning is None


class TestConfigWarnings:
    """A wrong-typed value or a wrong-shaped [keybindings] table is
    skipped field by field and named in the startup warning."""

    def _write(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = tmp_path / "vimtg"
        cfg.mkdir()
        (cfg / "config.toml").write_text(text, encoding="utf-8")

    def test_valid_config_has_no_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write(
            tmp_path, monkeypatch,
            '[editor]\nshow_prices = false\n[keybindings]\ns = ":w"\n'
            '[keybindings.normal]\nQ = ":q!"\n',
        )
        assert load_settings_checked() == (Settings(show_prices=False), None)

    def test_wrong_types_are_named(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write(
            tmp_path, monkeypatch,
            '[editor]\nsearch_limit = "many"\nshow_prices = 1\nprice_source = "gbp"\n'
            "auto_sort = false\n",
        )
        settings, warning = load_settings_checked()
        assert settings == Settings(auto_sort=False)
        assert warning is not None
        assert "search_limit must be a number" in warning
        assert "show_prices must be true or false" in warning
        assert "price_source = 'gbp' is not valid" in warning

    def test_bool_is_not_a_number(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write(tmp_path, monkeypatch, "[editor]\nsearch_limit = true\n")
        settings, warning = load_settings_checked()
        assert settings.search_limit == Settings().search_limit
        assert warning is not None and "search_limit" in warning

    def test_wrong_shape_keybindings_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write(
            tmp_path, monkeypatch,
            '[keybindings]\nnormal = "x"\nctrl_s = 3\n',
        )
        settings, warning = load_settings_checked()
        assert settings == Settings()
        assert warning is not None
        assert "[keybindings.normal] must be a table" in warning
        assert "keybindings.ctrl_s must be a string" in warning


class TestKeybindingProblems:
    def test_absent_table_is_fine(self) -> None:
        assert keybinding_problems(None) == []

    def test_not_a_table(self) -> None:
        assert keybinding_problems(["s"]) == ["[keybindings] must be a table"]

    def test_bad_mode_entry(self) -> None:
        assert keybinding_problems({"insert": {"ctrl_j": ["escape"]}}) == [
            "keybindings.insert.ctrl_j must be a string"
        ]

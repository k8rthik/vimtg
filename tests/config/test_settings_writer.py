"""Tests for TOML settings writer."""

import os

import pytest

from vimtg.config.settings import Settings
from vimtg.config.settings_writer import save_settings, settings_to_toml


class TestSettingsToToml:
    def test_default_settings_roundtrip(self) -> None:
        toml = settings_to_toml(Settings())
        assert "[editor]" in toml
        assert 'price_source = "usd"' in toml
        assert "show_prices = true" in toml
        assert "search_limit = 50" in toml

    def test_custom_settings(self) -> None:
        s = Settings(price_source="eur", show_prices=False, search_limit=100)
        toml = settings_to_toml(s)
        assert 'price_source = "eur"' in toml
        assert "show_prices = false" in toml
        assert "search_limit = 100" in toml

    def test_bool_values(self) -> None:
        s = Settings(auto_expand=False, confirm_quit=False)
        toml = settings_to_toml(s)
        assert "auto_expand = false" in toml
        assert "confirm_quit = false" in toml

    def test_empty_string_value(self) -> None:
        s = Settings(default_format="")
        toml = settings_to_toml(s)
        assert 'default_format = ""' in toml


class TestSaveSettings:
    def test_creates_config_file(self, tmp_path) -> None:
        os.environ["XDG_CONFIG_HOME"] = str(tmp_path)
        try:
            path = save_settings(Settings())
            assert path.exists()
            content = path.read_text()
            assert "[editor]" in content
            assert 'price_source = "usd"' in content
        finally:
            del os.environ["XDG_CONFIG_HOME"]

    def test_preserves_keybindings_section(self, tmp_path) -> None:
        config_dir = tmp_path / "vimtg"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            '[editor]\nprice_source = "usd"\n\n'
            '[keybindings]\ns = ":w"\nQ = ":q!"\n'
        )

        os.environ["XDG_CONFIG_HOME"] = str(tmp_path)
        try:
            save_settings(Settings(price_source="eur"))
            content = config_file.read_text()
            assert 'price_source = "eur"' in content
            assert "[keybindings]" in content
            assert 's = ":w"' in content
        finally:
            del os.environ["XDG_CONFIG_HOME"]

    def test_roundtrip_load_save(self, tmp_path) -> None:
        os.environ["XDG_CONFIG_HOME"] = str(tmp_path)
        try:
            original = Settings(
                price_source="tix", show_prices=False,
                search_limit=100, default_format="modern",
            )
            save_settings(original)

            from vimtg.config.settings import load_settings
            loaded = load_settings()
            assert loaded.price_source == "tix"
            assert loaded.show_prices is False
            assert loaded.search_limit == 100
            assert loaded.default_format == "modern"
        finally:
            del os.environ["XDG_CONFIG_HOME"]

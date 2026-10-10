"""Tests for TOML settings writer."""

import pytest

from vimtg.config.settings import Settings
from vimtg.config.settings_writer import (
    _format_value,
    save_settings,
    settings_to_toml,
)


class TestFormatValue:
    def test_bool(self) -> None:
        assert _format_value(True) == "true"
        assert _format_value(False) == "false"

    def test_int(self) -> None:
        assert _format_value(42) == "42"

    def test_str_escapes_quotes_and_backslash(self) -> None:
        assert _format_value('a"b\\c') == '"a\\"b\\\\c"'

    def test_other_falls_back_to_str(self) -> None:
        assert _format_value(1.5) == "1.5"


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
    def test_creates_config_file(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        path = save_settings(Settings())
        assert path.exists()
        content = path.read_text()
        assert "[editor]" in content
        assert 'price_source = "usd"' in content

    def test_preserves_keybindings_section(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_dir = tmp_path / "vimtg"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            '[editor]\nprice_source = "usd"\n\n'
            '[keybindings]\ns = ":w"\nQ = ":q!"\n'
        )

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        save_settings(Settings(price_source="eur"))
        content = config_file.read_text()
        assert 'price_source = "eur"' in content
        assert "[keybindings]" in content
        assert 's = ":w"' in content

    def test_roundtrip_load_save(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
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

    def test_preserves_nested_subtable(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_dir = tmp_path / "vimtg"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            '[editor]\nprice_source = "usd"\n\n'
            '[keybindings.normal]\ns = ":w"\n'
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        save_settings(Settings())
        content = config_file.read_text()
        assert "[keybindings.normal]" in content
        assert 's = ":w"' in content

    def test_failed_replace_cleans_up_temp(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        def boom(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError, match="disk full"):
            save_settings(Settings())

        # No leftover temp files in the config dir.
        cfg_dir = tmp_path / "vimtg"
        leftover = list(cfg_dir.glob("*.tmp")) if cfg_dir.exists() else []
        assert leftover == []


class TestSaveSettingsSafety:
    """Saving from :config must never corrupt or wipe config.toml."""

    @staticmethod
    def _config(tmp_path, monkeypatch: pytest.MonkeyPatch, text: str):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = tmp_path / "vimtg"
        cfg.mkdir()
        path = cfg / "config.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_quoted_keybinding_keys_stay_valid_toml(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import tomllib

        from vimtg.config.settings import load_settings_checked

        path = self._config(
            tmp_path, monkeypatch,
            '[editor]\nprice_source = "usd"\n\n'
            '[keybindings.normal]\n"ctrl+s" = ":w"\n"<leader>q" = ":q!"\n',
        )
        save_settings(Settings(price_source="eur"))

        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert data["keybindings"]["normal"] == {"ctrl+s": ":w", "<leader>q": ":q!"}
        settings, warning = load_settings_checked()
        assert warning is None
        assert settings.price_source == "eur"

    def test_other_value_types_survive(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import tomllib

        path = self._config(
            tmp_path, monkeypatch,
            '[editor]\ntheme = "dark"\nunknown_key = 1.5\n\n'
            '[extra]\nlist = [1, 2]\nnote = "tab\\there"\n'
            'inline = {a = 1}\n',
        )
        before = tomllib.loads(path.read_text(encoding="utf-8"))
        save_settings(Settings())
        after = tomllib.loads(path.read_text(encoding="utf-8"))
        assert after["extra"] == before["extra"]
        assert after["editor"]["unknown_key"] == 1.5

    def test_control_characters_escaped(self) -> None:
        import tomllib

        toml = settings_to_toml(Settings(theme="a\nb\x01c"))
        assert tomllib.loads(toml)["editor"]["theme"] == "a\nb\x01c"

    def test_unparseable_config_not_overwritten_and_backed_up(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from vimtg.config.settings_writer import SettingsWriteError

        broken = '[keybindings]\nctrl+s = ":w"\n'  # what the old writer produced
        path = self._config(tmp_path, monkeypatch, broken)
        with pytest.raises(SettingsWriteError, match="not valid TOML"):
            save_settings(Settings(price_source="eur"))
        assert path.read_text(encoding="utf-8") == broken
        backup = path.with_name("config.toml.bak")
        assert backup.read_text(encoding="utf-8") == broken

        # Retrying reuses the identical backup instead of piling up copies
        with pytest.raises(SettingsWriteError):
            save_settings(Settings())
        assert sorted(p.name for p in path.parent.iterdir()) == [
            "config.toml", "config.toml.bak",
        ]

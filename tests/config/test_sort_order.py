"""sort_order setting: defaults, validation, loading, and :set wiring."""

from __future__ import annotations

import pytest

from vimtg.config.settings import Settings, load_settings, validate_settings
from vimtg.editor.config_options import apply_setting, get_option
from vimtg.editor.sort_keys import SORT_FIELDS


class TestSortOrderSetting:
    def test_default_is_cmc(self) -> None:
        assert Settings().sort_order == "cmc"

    def test_validate_rejects_unknown(self) -> None:
        errors = validate_settings(Settings(sort_order="bogus"))
        assert any("sort_order" in e for e in errors)

    def test_option_registered_for_set_and_config_screen(self) -> None:
        opt = get_option("sort_order")
        assert opt is not None
        assert opt.option_type == "choice"
        # every choice is a real sort field
        assert set(opt.choices) <= SORT_FIELDS

    def test_apply_setting(self) -> None:
        s = apply_setting(Settings(), "sort_order", "power")
        assert s.sort_order == "power"

    def test_apply_setting_rejects_invalid(self) -> None:
        with pytest.raises(ValueError, match="sort_order"):
            apply_setting(Settings(), "sort_order", "bogus")

    def test_load_falls_back_on_invalid_value(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = tmp_path / "vimtg"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.toml").write_text(
            '[editor]\nsort_order = "bogus"\n', encoding="utf-8"
        )
        assert load_settings().sort_order == "cmc"

    def test_load_reads_valid_value(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = tmp_path / "vimtg"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.toml").write_text(
            '[editor]\nsort_order = "toughness"\n', encoding="utf-8"
        )
        assert load_settings().sort_order == "toughness"

"""The `collection` setting: a CSV path, empty by default, round-tripped
through config.toml and shown with the other options."""

from __future__ import annotations

from vimtg.config.paths import config_dir
from vimtg.config.settings import Settings, load_settings_checked
from vimtg.config.settings_writer import save_settings
from vimtg.editor.config_options import (
    apply_setting,
    cycle_setting,
    get_option,
    get_setting_display,
)


def test_default_is_empty() -> None:
    assert Settings().collection == ""


def test_round_trips_through_config_toml() -> None:
    save_settings(Settings(collection="~/cards/manabox.csv"))
    loaded, warning = load_settings_checked()
    assert warning is None
    assert loaded.collection == "~/cards/manabox.csv"


def test_a_windows_path_round_trips_through_config_toml() -> None:
    windows_path = "C:\\Users\\runner\\manabox.csv"
    save_settings(Settings(collection=windows_path))
    loaded, warning = load_settings_checked()
    assert warning is None
    assert loaded.collection == windows_path


def test_wrong_type_falls_back_with_a_warning() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    (config_dir() / "config.toml").write_text("[editor]\ncollection = 3\n", encoding="utf-8")
    loaded, warning = load_settings_checked()
    assert loaded.collection == ""
    assert warning is not None and "collection must be a string" in warning


def test_config_option_is_a_free_text_path() -> None:
    opt = get_option("collection")
    assert opt is not None
    assert opt.group == "Collection"
    assert get_setting_display(Settings(), "collection") == "Collection: none"
    changed = apply_setting(Settings(), "collection", "cards.csv")
    assert changed.collection == "cards.csv"
    assert cycle_setting(changed, "collection") == changed

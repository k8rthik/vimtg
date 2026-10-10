"""App-level file safety: new-file buffers, outside changes, config errors."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.config.settings import Settings
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine


def _message(app: VimTGApp) -> str:
    cl = app.screen.query_one("#command-line", CommandLine)
    return str(cl.render())


@pytest.mark.asyncio
async def test_missing_deck_path_opens_buffer_bound_to_it(tmp_path: Path) -> None:
    """`vimtg burn.deck` for a new file edits it (created on :w), like vim."""
    target = tmp_path / "burn.deck"
    app = VimTGApp(deck_path=target)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, MainScreen)
        assert screen.file_path == target
        assert not target.exists()
        screen._execute_ex("w")
        await pilot.pause()
        assert target.exists()
        assert "DCK:" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_write_refused_after_outside_change(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text("// Deck: Burn\n\nDCK:\n4 Lightning Bolt\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, MainScreen)

        deck.write_text("// edited in another editor, now longer\n", encoding="utf-8")
        screen._execute_ex("w")
        await pilot.pause()
        assert "changed on disk" in _message(app)
        assert deck.read_text(encoding="utf-8").startswith("// edited")

        screen._execute_ex("w!")
        await pilot.pause()
        assert "Lightning Bolt" in deck.read_text(encoding="utf-8")
        # The forced write re-stamps the file: a plain :w now succeeds
        screen._execute_ex("w")
        await pilot.pause()
        assert "Written" in _message(app)


@pytest.mark.asyncio
async def test_corrupt_config_warns_on_startup(tmp_path: Path) -> None:
    from vimtg.config.paths import config_dir

    (config_dir() / "config.toml").write_text("[editor\n", encoding="utf-8")
    app = VimTGApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        messages = [n.message for n in app._notifications]
        assert any("not valid TOML" in m for m in messages)


@pytest.mark.asyncio
async def test_settings_save_failure_is_visible(tmp_path: Path) -> None:
    from vimtg.config.paths import config_dir

    config = config_dir() / "config.toml"
    config.write_text('[keybindings]\nctrl+s = ":w"\n', encoding="utf-8")
    deck = tmp_path / "d.deck"
    deck.write_text("DCK:\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, MainScreen)
        screen._on_settings_saved(Settings(price_source="eur"))
        await pilot.pause()
        assert "not saved" in _message(app)
        # Applied for the session, file untouched
        assert app.settings.price_source == "eur"
        assert config.read_text(encoding="utf-8") == '[keybindings]\nctrl+s = ":w"\n'

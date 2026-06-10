"""Pilot-based integration tests for ConfigScreen (opened via :config)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.config_screen import ConfigScreen


async def _open_config(pilot) -> None:
    await pilot.press("colon")
    for ch in "config":
        await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_config_command_opens_config_screen(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_config(pilot)
        assert isinstance(app.screen, ConfigScreen)


@pytest.mark.asyncio
async def test_config_screen_navigation_and_close(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_config(pilot)
        # Navigate the option list and cycle a value — must not crash
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("k")
        await pilot.press("l")
        await pilot.press("h")
        await pilot.pause()
        assert isinstance(app.screen, ConfigScreen)
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, ConfigScreen)


@pytest.mark.asyncio
async def test_config_screen_escape_closes(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_config(pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ConfigScreen)

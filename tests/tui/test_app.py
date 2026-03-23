"""Minimal TUI app smoke tests using Textual's pilot API."""

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp


@pytest.mark.asyncio
async def test_app_starts() -> None:
    app = VimTGApp()
    async with app.run_test() as pilot:
        assert app.title == "vimtg"
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_app_loads_deck(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.press("escape")
        # Verify it loaded without crashing


@pytest.mark.asyncio
async def test_app_new_deck_without_path() -> None:
    app = VimTGApp(deck_path=None)
    async with app.run_test() as pilot:
        await pilot.press("escape")

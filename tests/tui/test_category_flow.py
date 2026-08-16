"""End-to-end category flow through the real key pipeline (Textual pilot)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine


def _deck(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "test.deck"
    path.write_text(text, encoding="utf-8")
    return path


def _main_screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


@pytest.mark.asyncio
async def test_gc_prompt_ghosts_and_applies(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "4 Cultivate\n4 Opt\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await pilot.press("w")  # scaffold metadata is prepended; go to a card
        card_row = screen._state.cursor.row
        assert screen._state.buffer.is_card_line(card_row)
        await pilot.press("g", "c")
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.prefix == "category: "

        # 'ra' ghosts the preset 'ramp'
        await pilot.press("r", "a")
        assert cl.ghost == "ramp"

        # Tab accepts the ghost, Enter applies it
        await pilot.press("tab")
        assert cl.text == "ramp"
        await pilot.press("enter")
        assert screen._state.buffer.category_at(card_row) == "ramp"


@pytest.mark.asyncio
async def test_gl_toggles_to_category_layout(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "4 Cultivate  @ramp\n4 Opt  @draw\n4 Shock\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await pilot.press("g", "l")
        text = screen._state.buffer.to_text()
        assert "// @ramp" in text
        assert "// @draw" in text
        assert "// Uncategorized" in text


@pytest.mark.asyncio
async def test_colon_layout_command(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "4 Cultivate  @ramp\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        for key in ":layout category":
            await pilot.press(key)
        await pilot.press("enter")
        assert "// @ramp" in screen._state.buffer.to_text()


@pytest.mark.asyncio
async def test_escape_cancels_category_prompt(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "4 Cultivate\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await pilot.press("g", "c", "r", "a", "escape")
        assert screen._state.buffer.category_at(0) == ""
        assert screen._state.mode_mgr.is_normal()

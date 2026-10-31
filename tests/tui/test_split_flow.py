"""Side-pane flow through the real key pipeline (Textual pilot): focus
moves with Ctrl-W w, :close closes, and the second-deck commands are gone."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.analytics_panel import AnalyticsPanel
from vimtg.tui.widgets.command_line import CommandLine


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "mine.deck"
    path.write_text("4 Lightning Bolt\n4 Shock\n", encoding="utf-8")
    return path


def _main_screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


async def _type_command(pilot, text: str) -> None:
    for ch in text:
        await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_ctrl_w_w_moves_focus_into_the_pane_and_back(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await _type_command(pilot, ":analytics")
        panel = screen.query_one("#analytics-panel", AnalyticsPanel)
        comp = screen._split_pane
        assert comp is not None and comp.focused is False
        assert panel.display is True

        main_row = screen._state.cursor.row
        await pilot.press("ctrl+w", "w")
        assert comp.focused is True
        assert panel.focused_panel is True
        await pilot.press("j")
        assert screen._state.cursor.row == main_row  # the pane took the key

        await pilot.press("ctrl+w", "w")
        assert comp.focused is False
        assert panel.focused_panel is False
        await pilot.press("j")
        assert screen._state.cursor.row == main_row + 1

        # Escape from a focused pane returns to the editor and keeps the pane
        await pilot.press("ctrl+w", "w", "escape")
        assert comp.focused is False and screen._split_pane is comp


@pytest.mark.asyncio
async def test_close_hides_the_pane(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await _type_command(pilot, ":analytics")
        await _type_command(pilot, ":close")
        assert screen._split_pane is None
        assert screen.query_one("#analytics-panel", AnalyticsPanel).display is False
        await _type_command(pilot, ":close")
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.error and "No pane open" in cl.message


@pytest.mark.asyncio
async def test_ctrl_w_w_without_a_pane_reports_it(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await pilot.press("ctrl+w", "w")
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.error
        assert "No pane open" in cl.message


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["vsplit other.deck", "split other.deck", "only"])
async def test_second_deck_commands_are_unknown(tmp_path: Path, command: str) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await _type_command(pilot, f":{command}")
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.error
        assert cl.message == f"E492: Not an editor command: {command}"
        assert screen._split_pane is None

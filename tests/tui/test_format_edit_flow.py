"""Format-field editing through the real key pipeline (Textual pilot)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.editor.cursor import Cursor
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "deck.deck"
    path.write_text("// Format:\n4 Lightning Bolt\n", encoding="utf-8")
    return path


def _on_format_line(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    buf = screen._state.buffer
    for i in range(buf.line_count()):
        if buf.get_line(i).text.startswith("// Format:"):
            screen._state.cursor = Cursor(row=i)
            return screen
    raise AssertionError("no // Format: line")


@pytest.mark.asyncio
async def test_format_ghost_tab_and_confirm(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _on_format_line(app)
        row = screen._state.cursor.row
        await pilot.press("i")
        cl = screen.query_one("#command-line", CommandLine)

        await pilot.press("c", "o", "m")
        assert cl.ghost == "commander"

        await pilot.press("tab")
        assert cl.text == "commander"

        await pilot.press("enter")
        assert screen._state.buffer.get_line(row).text == "// Format: commander"
        assert cl.message == ""


@pytest.mark.asyncio
async def test_unknown_format_notifies_on_confirm(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _on_format_line(app)
        row = screen._state.cursor.row
        await pilot.press("i")
        for ch in "edh":
            await pilot.press(ch)
        await pilot.press("enter")
        cl = screen.query_one("#command-line", CommandLine)
        assert "Unknown format 'edh'" in cl.message
        # And the format line carries a persistent lint warning sign
        screen._update_lint()
        err = screen._lint.line_errors.get(row)
        assert err is not None and "Unknown format" in err.message

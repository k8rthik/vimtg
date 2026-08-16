"""Split-pane flow through the real key pipeline (Textual pilot)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.editor.splits import SplitDirection
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.deck_view import DeckView


def _deck(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
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
async def test_vsplit_shows_second_deck(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "mine.deck", "4 Lightning Bolt\n")
    other = _deck(tmp_path, "other.deck", "4 Opt\n4 Consider\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        dv2 = screen.query_one("#deck-view-2", DeckView)
        assert dv2.display is False

        await _type_command(pilot, f":vsplit {other}")
        assert dv2.display is True
        assert screen._split_pane is not None
        assert screen._split_pane.direction is SplitDirection.VERTICAL
        assert dv2.buffer is not None
        assert "4 Opt" in dv2.buffer.to_text()
        # Main buffer untouched
        assert "Lightning Bolt" in screen._state.buffer.to_text()


@pytest.mark.asyncio
async def test_split_is_horizontal(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "mine.deck", "4 Lightning Bolt\n")
    other = _deck(tmp_path, "other.deck", "4 Opt\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await _type_command(pilot, f":split {other}")
        assert screen._split_pane is not None
        assert screen._split_pane.direction is SplitDirection.HORIZONTAL


@pytest.mark.asyncio
async def test_missing_file_reports_error(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "mine.deck", "4 Lightning Bolt\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await _type_command(pilot, f":vsplit {tmp_path}/nope.deck")
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.error
        assert "not found" in cl.message
        assert screen._split_pane is None


@pytest.mark.asyncio
async def test_close_hides_pane(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "mine.deck", "4 Lightning Bolt\n")
    other = _deck(tmp_path, "other.deck", "4 Opt\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await _type_command(pilot, f":vsplit {other}")
        await _type_command(pilot, ":close")
        assert screen._split_pane is None
        assert screen.query_one("#deck-view-2", DeckView).display is False


@pytest.mark.asyncio
async def test_ss_switches_focus_and_j_scrolls_companion(
    tmp_path: Path,
) -> None:
    deck = _deck(tmp_path, "mine.deck", "4 Lightning Bolt\n4 Shock\n")
    other = _deck(tmp_path, "other.deck", "4 Opt\n4 Consider\n4 Preordain\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await _type_command(pilot, f":vsplit {other}")
        comp = screen._split_pane
        assert comp is not None and comp.focused is False

        main_row = screen._state.cursor.row
        await pilot.press("S", "s")
        assert comp.focused is True

        await pilot.press("j")
        assert comp.cursor_row == 1
        assert screen._state.cursor.row == main_row  # editor cursor untouched

        # Escape returns focus to the editor; j moves the editor cursor again
        await pilot.press("escape")
        assert comp.focused is False
        await pilot.press("j")
        assert screen._state.cursor.row == main_row + 1
        assert comp.cursor_row == 1


@pytest.mark.asyncio
async def test_sc_closes_split(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "mine.deck", "4 Lightning Bolt\n")
    other = _deck(tmp_path, "other.deck", "4 Opt\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await _type_command(pilot, f":vsplit {other}")
        assert screen._split_pane is not None
        await pilot.press("S", "c")
        assert screen._split_pane is None


@pytest.mark.asyncio
async def test_sv_prefills_command_line(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "mine.deck", "4 Lightning Bolt\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await pilot.press("S", "v")
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.prefix == ":"
        assert cl.text == "vsplit "


@pytest.mark.asyncio
async def test_ss_without_split_reports_error(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "mine.deck", "4 Lightning Bolt\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await pilot.press("S", "s")
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.error
        assert "No split open" in cl.message

"""Analytics pane flow (Textual pilot): open via :analytics / Sa, live
updates on edit, cursor-following odds, close via :close."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.analytics_panel import AnalyticsPanel

_DECK = (
    "// Creature\n"
    "4 Goblin Guide\n"
    "\n"
    "// Land\n"
    "20 Mountain\n"
)


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(_DECK, encoding="utf-8")
    return path


def _main_screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


async def _open_analytics(pilot, app: VimTGApp) -> AnalyticsPanel:  # type: ignore[no-untyped-def]
    for ch in ":analytics":
        await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause()
    return _main_screen(app).query_one("#analytics-panel", AnalyticsPanel)


@pytest.mark.asyncio
async def test_analytics_opens_unfocused_pane(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        panel = await _open_analytics(pilot, app)
        assert panel.display is True
        assert panel.data is not None
        comp = screen._split_pane
        assert comp is not None
        assert comp.kind == "analytics"
        assert comp.focused is False  # editing continues in the deck


@pytest.mark.asyncio
async def test_sa_key_opens_pane(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        await pilot.press("S")
        await pilot.press("a")
        await pilot.pause()
        comp = screen._split_pane
        assert comp is not None
        assert comp.kind == "analytics"


@pytest.mark.asyncio
async def test_pane_updates_on_edit(tmp_path: Path) -> None:
    from vimtg.editor.cursor import Cursor

    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        panel = await _open_analytics(pilot, app)
        before = panel.data
        assert before is not None
        row = screen._state.buffer.next_card_line(0)
        assert row is not None
        screen._state.cursor = Cursor(row=row)
        await pilot.press("plus")
        await pilot.pause()
        after = panel.data
        assert after is not None
        assert after is not before  # recomputed for the new buffer
        assert after.stats.mainboard_count == before.stats.mainboard_count + 1


@pytest.mark.asyncio
async def test_cursor_card_follows_cursor(tmp_path: Path) -> None:
    from vimtg.editor.cursor import Cursor

    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _main_screen(app)
        panel = await _open_analytics(pilot, app)
        buf = screen._state.buffer
        row = next(
            i for i in range(buf.line_count())
            if buf.card_name_at(i) == "Goblin Guide"
        )
        screen._state.cursor = Cursor(row=row)
        screen._sync_widgets()
        assert panel.cursor_card == ("Goblin Guide", 4)
        screen._state.cursor = Cursor(row=0)  # metadata/header line
        screen._sync_widgets()
        assert panel.cursor_card is None


@pytest.mark.asyncio
async def test_close_hides_pane(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        panel = await _open_analytics(pilot, app)
        for ch in ":close":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert panel.display is False
        assert _main_screen(app)._split_pane is None

"""Trackpad/mouse wheel scrolling through the real app."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.widgets.deck_view import DeckView


def _deck(tmp_path: Path) -> Path:
    p = tmp_path / "big.deck"
    p.write_text("// Lands\n" + "".join(f"1 Card {i}\n" for i in range(80)), encoding="utf-8")
    return p


@pytest.mark.asyncio
async def test_wheel_scrolls_deck_and_cursor_follows(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        dv = screen.query_one("#deck-view", DeckView)
        assert screen._state.cursor.row == 0  # type: ignore[attr-defined]
        for _ in range(8):
            dv.wheel(3)
        await pilot.pause()
        assert dv._scroll_offset == 24
        # The cursor was dragged into the window rather than left off-screen
        assert screen._state.cursor.row >= 24  # type: ignore[attr-defined]
        row_after_down = screen._state.cursor.row  # type: ignore[attr-defined]
        for _ in range(8):
            dv.wheel(-3)
        await pilot.pause()
        assert dv._scroll_offset == 0
        # ...and dragged back up so it stays inside the window
        assert screen._state.cursor.row < row_after_down  # type: ignore[attr-defined]
        assert screen._state.cursor.row <= dv.size.height - 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_wheel_ignored_while_inserting(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        dv = screen.query_one("#deck-view", DeckView)
        await pilot.press("o")
        await pilot.pause()
        row = screen._state.cursor.row  # type: ignore[attr-defined]
        dv.wheel(3)
        await pilot.pause()
        assert screen._state.cursor.row == row  # type: ignore[attr-defined]

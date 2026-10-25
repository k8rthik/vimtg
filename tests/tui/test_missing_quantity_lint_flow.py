"""A '4x Shock' line in the editor gets a warning sign and a reason."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.deck_view import DeckView
from vimtg.tui.widgets.status_line import StatusLine


@pytest.mark.asyncio
async def test_nx_line_is_flagged_in_the_editor(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    deck.write_text(
        "// Deck: Burn\n// Format:\n// Tags:\n\n4x Shock\n56 Mountain\n", encoding="utf-8"
    )
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, MainScreen)
        row = screen._state.buffer.to_text().split("\n").index("4x Shock")
        view = screen.query_one("#deck-view", DeckView)
        assert view.line_errors[row].message == "not a card line: drop the x (4 Shock)"
        await pilot.press("G")
        await pilot.press("k")
        await pilot.pause()
        assert screen._state.cursor.row == row
        status = screen.query_one("#status-line", StatusLine)
        assert status.cursor_lint == "not a card line: drop the x (4 Shock)"
        assert status.cursor_lint_level == "warning"

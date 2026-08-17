"""o/O on metadata through the real key pipeline (Textual pilot)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.editor.buffer import LineType
from vimtg.editor.cursor import Cursor
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen


def _screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


def _metadata_rows(screen: MainScreen) -> list[int]:
    buf = screen._state.buffer
    return [
        i for i in range(buf.line_count())
        if buf.get_line(i).line_type is LineType.METADATA
    ]


@pytest.mark.asyncio
async def test_shift_o_on_metadata_keeps_block_contiguous(
    tmp_path: Path,
) -> None:
    deck = tmp_path / "deck.deck"
    deck.write_text("// Deck: Burn\n// Format: modern\n\n4 Lightning Bolt\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _screen(app)
        rows = _metadata_rows(screen)
        # Cursor on a metadata line inside the block, open above
        screen._state.cursor = Cursor(row=rows[-1])
        await pilot.press("O")
        new_rows = _metadata_rows(screen)
        assert new_rows == list(range(new_rows[0], new_rows[0] + len(rows)))
        # Cancel: the metadata block must still be contiguous
        await pilot.press("escape")
        final_rows = _metadata_rows(screen)
        assert final_rows == list(
            range(final_rows[0], final_rows[0] + len(rows))
        )

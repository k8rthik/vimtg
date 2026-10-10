"""H / M / L and n / N through the real app and a rendered deck view."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.widgets.deck_view import DeckView


def _deck(tmp_path: Path) -> Path:
    p = tmp_path / "big.deck"
    p.write_text("// Lands\n" + "".join(f"1 Card {i}\n" for i in range(80)), encoding="utf-8")
    return p


def _row(app: VimTGApp) -> int:
    return app.screen._state.cursor.row  # type: ignore[attr-defined, no-any-return]


@pytest.mark.asyncio
async def test_hml_stay_inside_the_view(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        dv = app.screen.query_one("#deck-view", DeckView)
        # Scroll into the middle so neither end of the window is the
        # buffer's end and the scrolloff margin applies on both sides
        await pilot.press("4", "0", "G")
        await pilot.pause()
        band = dv.cursor_band()
        assert band is not None
        top, bottom = band
        assert 0 < top < bottom
        offset = dv._scroll_offset

        await pilot.press("H")
        await pilot.pause()
        assert _row(app) == top
        assert dv._scroll_offset == offset  # the view did not move

        await pilot.press("L")
        await pilot.pause()
        assert top < _row(app) <= bottom

        await pilot.press("M")
        await pilot.pause()
        assert top < _row(app) < bottom


@pytest.mark.asyncio
async def test_h_at_top_of_buffer_reaches_first_line(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("j", "j", "j", "j", "H")
        await pilot.pause()
        assert _row(app) == 0


@pytest.mark.asyncio
async def test_find_then_n_and_shift_n(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("slash", "5", "dollar_sign")
        await pilot.press("enter")
        await pilot.pause()
        # The app prepends a 4-line metadata header: "Card N" is row N + 5
        assert _row(app) == 10  # "1 Card 5"
        await pilot.press("n")
        await pilot.pause()
        assert _row(app) == 20  # "1 Card 15"
        await pilot.press("2", "n")
        await pilot.pause()
        assert _row(app) == 40  # "1 Card 35"
        await pilot.press("N")
        await pilot.pause()
        assert _row(app) == 30

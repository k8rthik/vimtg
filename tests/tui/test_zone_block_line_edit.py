"""`i` on a card line inside a `DCK:` / `CMD:` block (or a `VS:` plan)
keeps the block indentation locked, and so does `.` repeating the edit,
so the card stays in its zone. `i` on a bare zone header is refused, as
vim refuses to edit what cannot be changed."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine

_DECK = (
    "// Deck: Krenko\n// Format: commander\n// Tags:\n\n"
    "CMD:\n    1 Krenko, Mob Boss\n\n"
    "DCK:\n    1 Goblin Guide\n    20 Mountain\n"
)


def _rows(screen: MainScreen) -> list[str]:
    return screen._state.buffer.to_text().splitlines()


async def _open(pilot_app: VimTGApp, pilot, text: str) -> MainScreen:  # type: ignore[no-untyped-def]
    await pilot.pause()
    screen = pilot_app.screen
    assert isinstance(screen, MainScreen)
    row = _rows(screen).index(text)
    screen._state.cursor = screen._state.cursor.move_to(row, 0)
    screen._sync_widgets()
    return screen


@pytest.mark.asyncio
async def test_i_and_dot_in_a_block_keep_the_indentation(tmp_path: Path) -> None:
    deck = tmp_path / "krenko.deck"
    deck.write_text(_DECK, encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = await _open(app, pilot, "    1 Goblin Guide")
        await pilot.press("i")
        await pilot.pause()
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.text == "1 Goblin Guide"
        await pilot.press("ctrl+u")
        for ch in "4 Goblin Guide":
            await pilot.press("space" if ch == " " else ch)
        await pilot.press("enter")
        await pilot.pause()
        rows = _rows(screen)
        assert rows[rows.index("DCK:") + 1] == "    4 Goblin Guide"
        await pilot.press("j", ".")
        await pilot.pause()
        rows = _rows(screen)
        assert rows[rows.index("DCK:") + 2] == "    4 Goblin Guide"


@pytest.mark.asyncio
@pytest.mark.parametrize("header", ["DCK:", "CMD:"])
async def test_i_on_a_zone_header_is_refused(tmp_path: Path, header: str) -> None:
    deck = tmp_path / "krenko.deck"
    deck.write_text(_DECK, encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = await _open(app, pilot, header)
        await pilot.press("i")
        await pilot.pause()
        assert screen._state.mode_mgr.is_normal()
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.error and cl.message.startswith("E21:")
        assert header in cl.message
        assert header in _rows(screen)

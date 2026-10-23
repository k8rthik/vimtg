"""`:enew` and `:import` open a new unnamed buffer in place of the deck,
as vim's :enew does and as the greeter's new-deck and import do: the
deck that was open is left as it is on disk, and the first `:w` names
the new one after its `// Deck:` line. Unsaved changes refuse with E37
unless the command has `!`."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.tui.test_url_import_flow import _REMOTE, _URL
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.screens.new_deck import NewDeckScreen
from vimtg.tui.widgets.command_line import CommandLine

_OLD = "// Deck: Old\n\n4 Goblin Guide\n"


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "old.deck"
    path.write_text(_OLD, encoding="utf-8")
    return path


def _list(tmp_path: Path) -> Path:
    path = tmp_path / "list.txt"
    path.write_text("4 Lightning Bolt\n20 Mountain\n", encoding="utf-8")
    return path


def _main(app: VimTGApp) -> MainScreen:
    return next(s for s in reversed(app.screen_stack) if isinstance(s, MainScreen))


async def _ex(app: VimTGApp, pilot, text: str) -> None:  # type: ignore[no-untyped-def]
    _main(app)._execute_ex(text)
    await app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.pause()


def _message(app: VimTGApp) -> CommandLine:
    return _main(app).query_one("#command-line", CommandLine)


@pytest.mark.asyncio
async def test_import_file_opens_an_unnamed_buffer(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    deck = _deck(tmp_path)
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        await pilot.pause()
        old = _main(app)
        await _ex(app, pilot, f"import {_list(tmp_path)}")
        new = _main(app)
        assert new is not old
        assert new.file_path is None
        assert "4 Lightning Bolt" in new._state.buffer.to_text()
        assert new._state.modified
        assert "Imported" in _message(app).message
        await _ex(app, pilot, "w")
        assert deck.read_text(encoding="utf-8") == _OLD
        assert new.file_path is not None and new.file_path != deck


@pytest.mark.asyncio
async def test_url_import_opens_an_unnamed_buffer(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    deck = _deck(tmp_path)
    app = VimTGApp(deck_path=deck)
    with patch("vimtg.tui.screens.main_screen.fetch_deck", return_value=_REMOTE):
        async with app.run_test() as pilot:
            await pilot.pause()
            await _ex(app, pilot, f"import {_URL}")
            new = _main(app)
            assert new.file_path is None
            assert "4 Lightning Bolt" in new._state.buffer.to_text()
            assert _message(app).message.startswith("Imported 27 cards from moxfield.com")
    assert deck.read_text(encoding="utf-8") == _OLD


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["import {list}", f"import {_URL}", "enew"])
async def test_unsaved_changes_refuse_with_e37(tmp_path: Path, command: str) -> None:
    os.chdir(tmp_path)
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch("vimtg.tui.screens.main_screen.fetch_deck", return_value=_REMOTE) as fetch:
        async with app.run_test() as pilot:
            await pilot.pause()
            old = _main(app)
            await pilot.press("G", "plus")
            await _ex(app, pilot, command.format(list=_list(tmp_path)))
            assert _main(app) is old
            cl = _message(app)
            assert cl.message.startswith("E37:") and cl.error
            assert "5 Goblin Guide" in old._state.buffer.to_text()
            fetch.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["import! {list}", "enew!"])
async def test_bang_discards_unsaved_changes(tmp_path: Path, command: str) -> None:
    os.chdir(tmp_path)
    deck = _deck(tmp_path)
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        await pilot.pause()
        old = _main(app)
        await pilot.press("G", "plus")
        await _ex(app, pilot, command.format(list=_list(tmp_path)))
        assert _main(app) is not old
        assert _main(app).file_path is None
    assert deck.read_text(encoding="utf-8") == _OLD


@pytest.mark.asyncio
async def test_enew_opens_the_new_deck_wizard(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        old = _main(app)
        _main(app)._execute_ex("enew")
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, NewDeckScreen)
        new = _main(app)
        assert new is not old and new.file_path is None
        assert "Goblin Guide" not in new._state.buffer.to_text()


@pytest.mark.asyncio
async def test_edits_made_during_a_url_fetch_are_kept(tmp_path: Path) -> None:
    """The fetch runs in the background: edits made meanwhile are not
    thrown away by the deck arriving."""
    os.chdir(tmp_path)
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch("vimtg.tui.screens.main_screen.fetch_deck", return_value=_REMOTE):
        async with app.run_test() as pilot:
            await pilot.pause()
            old = _main(app)
            old._state.modified = True
            old._url_import_loaded(_REMOTE, _URL, old._import_generation, False)
            await pilot.pause()
            assert _main(app) is old
            assert _message(app).message.startswith("E37:")

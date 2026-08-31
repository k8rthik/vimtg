"""':import <url>' flow with a stubbed fetcher (Textual pilot)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
from vimtg.services.deck_sources import DeckSourceError, RemoteDeck
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine

_REMOTE = RemoteDeck(
    name="Mono Red Burn",
    deck=Deck(
        metadata=DeckMetadata(),
        entries=(
            DeckEntry(4, "Lightning Bolt", DeckSection.MAIN),
            DeckEntry(20, "Mountain", DeckSection.MAIN),
            DeckEntry(2, "Rest in Peace", DeckSection.SIDEBOARD),
            DeckEntry(1, "Opt", DeckSection.MAYBEBOARD),
        ),
        comments=(),
    ),
)

_URL = "https://moxfield.com/decks/abc123"


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "old.deck"
    path.write_text("4 Goblin Guide\n", encoding="utf-8")
    return path


def _main_screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


async def _run_import(pilot, app: VimTGApp, url: str = _URL) -> MainScreen:  # type: ignore[no-untyped-def]
    for ch in f":import {url}":
        await pilot.press(ch)
    await pilot.press("enter")
    await app.workers.wait_for_complete()
    await pilot.pause()
    return _main_screen(app)


@pytest.mark.asyncio
async def test_url_import_replaces_buffer(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(
        "vimtg.tui.screens.main_screen.fetch_deck", return_value=_REMOTE
    ) as fetched:
        async with app.run_test() as pilot:
            screen = await _run_import(pilot, app)
            text = screen._state.buffer.to_text()
            assert fetched.call_args[0][0] == _URL
            assert "4 Lightning Bolt" in text
            assert "4 Goblin Guide" not in text  # old buffer replaced
            assert "// Deck: Mono Red Burn" in text
            assert f"// Source: {_URL}" in text
            # Zones survive: sideboard and maybeboard lines exist
            assert "Rest in Peace" in text
            assert "Opt" in text
            assert screen._state.modified


@pytest.mark.asyncio
async def test_url_import_is_undoable(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(
        "vimtg.tui.screens.main_screen.fetch_deck", return_value=_REMOTE
    ):
        async with app.run_test() as pilot:
            screen = await _run_import(pilot, app)
            await pilot.press("u")
            await pilot.pause()
            assert "4 Goblin Guide" in screen._state.buffer.to_text()


@pytest.mark.asyncio
async def test_url_import_failure_shows_error(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(
        "vimtg.tui.screens.main_screen.fetch_deck",
        side_effect=DeckSourceError("Could not fetch deck (HTTP 404)"),
    ):
        async with app.run_test() as pilot:
            screen = await _run_import(pilot, app)
            cl = screen.query_one("#command-line", CommandLine)
            assert "404" in cl.message
            assert "4 Goblin Guide" in screen._state.buffer.to_text()

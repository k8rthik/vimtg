"""The o/O card-search overlay speaks the full search syntax."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.search_results import SearchResults

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "scryfall_real_shape.json"


@pytest.fixture
def seeded_db(db_factory):  # type: ignore[no-untyped-def]
    db_file = db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    repo = CardRepository(db_factory(db_file))
    repo.replace_all(
        [Card.from_scryfall(d) for d in json.loads(_FIXTURES.read_text(encoding="utf-8"))]
    )
    return repo


def _deck(tmp_path: Path, header: str = "") -> Path:
    path = tmp_path / "deck.deck"
    path.write_text(f"{header}4 Lightning Bolt\n", encoding="utf-8")
    return path


async def _type_search(pilot, app: VimTGApp, query: str) -> MainScreen:  # type: ignore[no-untyped-def]
    await pilot.press("o")
    for ch in query:
        await pilot.press("space" if ch == " " else ch)
    await app.workers.wait_for_complete()
    await pilot.pause()
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


@pytest.mark.asyncio
async def test_filters_and_negation(seeded_db, tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = await _type_search(pilot, app, "t:creature -c:w")
        sr = screen.query_one("#search-results", SearchResults)
        got = {c.name for c in sr.results}
        assert "Thrasios, Triton Hero" in got
        assert "Tymna the Weaver" not in got
        assert sr.error == ""


@pytest.mark.asyncio
async def test_unknown_key_named_and_query_kept(seeded_db, tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = await _type_search(pilot, app, "foo:bar")
        sr = screen.query_one("#search-results", SearchResults)
        assert sr.display is True
        assert sr.results == []
        assert sr.error == "Unknown search key 'foo'"
        assert "Unknown search key 'foo'" in str(sr.render())
        # The typed query stays on the prompt
        assert screen.query_one("#command-line", CommandLine).text == "foo:bar"

        # Fixing the query clears the error
        for _ in range(7):
            await pilot.press("backspace")
        for ch in "bolt":
            await pilot.press(ch)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert sr.error == ""
        assert any(c.name == "Lightning Bolt" for c in sr.results)


@pytest.mark.asyncio
async def test_format_filter_applies_before_search_limit(
    seeded_db, tmp_path: Path
) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path, "// Format: pauper\n"))
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, MainScreen)
        screen._state.settings = replace(screen._state.settings, search_limit=2)
        await _type_search(pilot, app, "mv>=0")
        sr = screen.query_one("#search-results", SearchResults)
        # Sorted by name, eight non-pauper cards come first; the format
        # filter must not leave the overlay empty.
        assert [c.name for c in sr.results] == [
            "Delver of Secrets // Insectile Aberration", "Lightning Bolt"
        ]


@pytest.mark.asyncio
async def test_stale_worker_results_are_dropped(seeded_db, tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = await _type_search(pilot, app, "bolt")
        sr = screen.query_one("#search-results", SearchResults)
        bolt = sr.results[0]
        # A slow worker for an earlier keystroke finishes last
        screen._apply_search_results("bo", [])
        screen._show_search_error("bo", "stale")
        assert sr.results == [bolt]
        assert sr.error == ""

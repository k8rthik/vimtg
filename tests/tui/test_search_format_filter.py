"""Card search must survive non-canonical // Format: values.

Regression: '// Format: Commander' (capitalized, as most sites export)
was used raw as a Scryfall legalities key, silently filtering every
search result to nothing — the overlay just never appeared.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.search_results import SearchResults

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "scryfall_sample.json"


@pytest.fixture
def seeded_db(db_factory):  # type: ignore[no-untyped-def]
    """Card DB at the app's real db_path (XDG is test-isolated)."""
    db_file = db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    repo = CardRepository(db_factory(db_file))
    repo.bulk_insert(
        [Card.from_scryfall(d) for d in json.loads(_FIXTURES.read_text())]
    )
    return repo


def _deck(tmp_path: Path, format_line: str) -> Path:
    path = tmp_path / "deck.deck"
    path.write_text(f"{format_line}\n4 Goblin Guide\n", encoding="utf-8")
    return path


async def _search(pilot, app: VimTGApp, query: str) -> SearchResults:
    await pilot.press("o")
    for ch in query:
        await pilot.press(ch)
    await app.workers.wait_for_complete()
    await pilot.pause()
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen.query_one("#search-results", SearchResults)


@pytest.mark.asyncio
async def test_capitalized_format_still_finds_cards(
    seeded_db, tmp_path: Path,
) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path, "// Format: Commander"))
    async with app.run_test() as pilot:
        sr = await _search(pilot, app, "light")
        assert sr.display is True
        assert any(c.name == "Lightning Bolt" for c in sr.results)


@pytest.mark.asyncio
async def test_unknown_format_does_not_empty_results(
    seeded_db, tmp_path: Path,
) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path, "// Format: edh"))
    async with app.run_test() as pilot:
        sr = await _search(pilot, app, "light")
        assert sr.display is True
        assert sr.results


@pytest.mark.asyncio
async def test_known_format_still_filters_illegal_cards(
    seeded_db, tmp_path: Path,
) -> None:
    # The fixture's Lightning Bolt is not standard-legal
    app = VimTGApp(deck_path=_deck(tmp_path, "// Format: standard"))
    async with app.run_test() as pilot:
        sr = await _search(pilot, app, "light")
        assert not any(c.name == "Lightning Bolt" for c in sr.results)

"""Sideboard-plan flow (Textual pilot): :plan creates a block, mo/mi
write into it, the deck view annotates deltas, o inside the block adds
a signed line, undo reverts, and the analytics pane boards the deck."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card
from vimtg.editor.cursor import Cursor
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.analytics_panel import AnalyticsPanel
from vimtg.tui.widgets.deck_view import DeckView
from vimtg.tui.widgets.status_line import StatusLine

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "scryfall_sample.json"

_DECK = (
    "// Deck: Burn\n"
    "// Format: modern\n"
    "\n"
    "DCK:\n"
    "    4 Lightning Bolt\n"
    "    4 Goblin Guide\n"
    "\n"
    "SB:\n"
    "    3 Rest in Peace\n"
)


@pytest.fixture
def seeded_db(db_factory):  # type: ignore[no-untyped-def]
    db_file = db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    repo = CardRepository(db_factory(db_file))
    repo.bulk_insert(
        [Card.from_scryfall(d) for d in json.loads(_FIXTURES.read_text())]
    )
    return repo


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(_DECK, encoding="utf-8")
    return path


def _screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


def _row_of(screen: MainScreen, text: str) -> int:
    buf = screen._state.buffer
    for i in range(buf.line_count()):
        if buf.get_line(i).text.strip() == text:
            return i
    raise AssertionError(f"line not found: {text}")


def _lines(screen: MainScreen) -> list[str]:
    buf = screen._state.buffer
    return [buf.get_line(i).text for i in range(buf.line_count())]


async def _ex(pilot, text: str) -> None:  # type: ignore[no-untyped-def]
    for ch in f":{text}":
        await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause()


async def _goto(pilot, screen: MainScreen, text: str) -> None:  # type: ignore[no-untyped-def]
    screen._state.cursor = Cursor(row=_row_of(screen, text))
    await pilot.press("l")  # any key: resync widgets from state
    await pilot.pause()


@pytest.mark.asyncio
async def test_plan_creates_block_and_boards_cards(seeded_db, tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _screen(app)
        await _ex(pilot, "plan Tron")
        assert "VS: Tron" in _lines(screen)
        assert screen._state.active_plan == "Tron"
        assert screen._state.cursor.row == _row_of(screen, "VS: Tron")

        await _goto(pilot, screen, "4 Lightning Bolt")
        await pilot.press("z")
        await pilot.press("o")
        await pilot.pause()
        assert "    -4 Lightning Bolt" in _lines(screen)
        assert screen._state.cursor.row == _row_of(screen, "4 Lightning Bolt")

        await _goto(pilot, screen, "3 Rest in Peace")
        await pilot.press("2")
        await pilot.press("z")
        await pilot.press("i")
        await pilot.pause()
        assert "    +2 Rest in Peace" in _lines(screen)

        dv = screen.query_one("#deck-view", DeckView)
        assert dv.plan_deltas == {
            _row_of(screen, "4 Lightning Bolt"): -4,
            _row_of(screen, "3 Rest in Peace"): 2,
        }
        sl = screen.query_one("#status-line", StatusLine)
        assert sl.plan_status == "vs Tron -4/+2"
        assert sl.plan_unbalanced is True

        await pilot.press("u")
        await pilot.pause()
        assert "    +2 Rest in Peace" not in _lines(screen)


@pytest.mark.asyncio
async def test_o_inside_a_plan_adds_a_signed_line(seeded_db, tmp_path: Path) -> None:
    deck = _deck(tmp_path)
    deck.write_text(_DECK + "\nVS: Tron\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _screen(app)
        await _goto(pilot, screen, "VS: Tron")
        await pilot.press("o")
        for ch in "rest":
            await pilot.press(ch)
        await pilot.pause()
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert "    +1 Rest in Peace" in _lines(screen)

        await pilot.press("o")
        for ch in "gobl":
            await pilot.press(ch)
        await pilot.pause()
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert "    -1 Goblin Guide" in _lines(screen)


@pytest.mark.asyncio
async def test_analytics_pane_boards_the_deck(seeded_db, tmp_path: Path) -> None:
    deck = _deck(tmp_path)
    deck.write_text(
        _DECK + "\nVS: Tron\n    -4 Goblin Guide\n    +3 Rest in Peace\n",
        encoding="utf-8",
    )
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _screen(app)
        await _ex(pilot, "analytics")
        panel = screen.query_one("#analytics-panel", AnalyticsPanel)
        assert panel.data is not None
        assert panel.data.stats.mainboard_count == 8
        assert panel.plan_name == ""

        await _ex(pilot, "plan Tron")
        assert panel.plan_name == "Tron"
        assert panel.data.stats.mainboard_count == 7
        assert "vs Tron" in panel.render().plain

        await _ex(pilot, "plan!")
        assert panel.plan_name == ""
        assert panel.data.stats.mainboard_count == 8


@pytest.mark.asyncio
async def test_save_round_trips_the_plan(seeded_db, tmp_path: Path) -> None:
    deck = _deck(tmp_path)
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = _screen(app)
        await _ex(pilot, "plan Tron")
        await _goto(pilot, screen, "4 Goblin Guide")
        await pilot.press("z")
        await pilot.press("o")
        await pilot.pause()
        await _ex(pilot, "w")
    assert deck.read_text().endswith("\nVS: Tron\n    -4 Goblin Guide\n")

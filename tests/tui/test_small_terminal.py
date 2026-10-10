"""Small terminals degrade gracefully (checked with Textual's pilot at
several sizes): overlays cap at about half the screen, the greeter sheds
its logo before its menu, extras hide, and below the minimum a notice
replaces the garbled layout."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.greeter import ACTIONS, GreeterScreen, GreeterView
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.screens.too_small import MIN_HEIGHT, MIN_WIDTH, TooSmallScreen
from vimtg.tui.widgets.search_results import SearchResults
from vimtg.tui.widgets.tips_panel import TipsPanel

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "scryfall_sample.json"
_DECK = "// Deck: Burn\n// Format: modern\n\n4 Lightning Bolt\n4 Goblin Guide\n"


@pytest.fixture
def seeded_db(db_factory):  # type: ignore[no-untyped-def]
    db_file = db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    repo = CardRepository(db_factory(db_file))
    repo.bulk_insert(
        [Card.from_scryfall(d) for d in json.loads(_FIXTURES.read_text())]
    )
    return repo


def _deck(tmp_path: Path, text: str = _DECK) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(text, encoding="utf-8")
    return path


def _main(app: VimTGApp) -> MainScreen:
    for screen in reversed(app.screen_stack):
        if isinstance(screen, MainScreen):
            return screen
    raise AssertionError("no MainScreen")


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(40, 12), (80, 24), (120, 50)])
async def test_search_overlay_leaves_the_deck_visible(
    seeded_db, tmp_path: Path, size: tuple[int, int]  # type: ignore[no-untyped-def]
) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await pilot.press("o")
        for ch in "li":
            await pilot.press(ch)
        await app.workers.wait_for_complete()
        await pilot.pause()
        sr = _main(app).query_one("#search-results", SearchResults)
        assert sr.display is True
        assert 0 < sr.size.height <= size[1] // 2
        deck_view = _main(app).query_one("#deck-view")
        assert deck_view.size.height >= 2


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(20, 6), (29, 20), (80, 7)])
async def test_below_minimum_shows_notice(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TooSmallScreen)
        text = str(app.screen.query_one("#too-small").render())
        assert "too small" in text
        assert f"{MIN_WIDTH}x{MIN_HEIGHT}" in text
        # Keys typed blind never reach the editor
        await pilot.press("d")
        await pilot.press("d")
        assert "Lightning Bolt" in _main(app)._state.buffer.to_text()


@pytest.mark.asyncio
async def test_notice_goes_away_when_terminal_grows(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(20, 6)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TooSmallScreen)
        await pilot.resize_terminal(25, 6)
        await pilot.pause()
        assert "25x6" in str(app.screen.query_one("#too-small").render())
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)
        await pilot.resize_terminal(20, 6)
        await pilot.pause()
        assert isinstance(app.screen, TooSmallScreen)


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(30, 8), (40, 12), (80, 24)])
async def test_greeter_menu_always_fully_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, size: tuple[int, int]
) -> None:
    monkeypatch.chdir(tmp_path)
    app = VimTGApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, GreeterScreen)
        gv = app.screen.query_one(GreeterView)
        rendered = gv.render()
        lines = rendered.plain.rstrip("\n").split("\n")
        assert len(lines) <= size[1]
        assert all(len(line) <= size[0] for line in lines)
        for key, _label in ACTIONS:
            assert f"[{key}]" in rendered.plain
        has_logo = "___/" in rendered.plain
        assert has_logo is (size[1] >= 24)


@pytest.mark.asyncio
async def test_tips_panel_yields_to_a_short_terminal(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "// Deck: E\n// Format: modern\n\nDCK:\n")
    app = VimTGApp(deck_path=deck)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        tips = _main(app).query_one("#tips-panel", TipsPanel)
        assert tips.display is True
        await pilot.resize_terminal(80, 12)
        await pilot.pause()
        assert tips.display is False
        await pilot.resize_terminal(80, 30)
        await pilot.pause()
        assert tips.display is True


@pytest.mark.asyncio
async def test_side_split_hidden_when_too_narrow(tmp_path: Path) -> None:
    other = tmp_path / "other.deck"
    other.write_text("4 Shock\n", encoding="utf-8")
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = _main(app)
        screen._execute_ex(f"vsplit {other}")
        await pilot.pause()
        pane = screen.query_one("#deck-view-2")
        assert pane.display is True
        await pilot.resize_terminal(40, 30)
        await pilot.pause()
        assert pane.display is False
        assert screen.query_one("#deck-view").size.width >= 38
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        assert pane.display is True


@pytest.mark.asyncio
async def test_new_deck_wizard_fits_a_small_terminal(tmp_path: Path) -> None:
    from vimtg.tui.screens.new_deck import NewDeckScreen

    app = VimTGApp(deck_path=tmp_path / "new.deck")
    async with app.run_test(size=(40, 12)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, NewDeckScreen)
        box = app.screen.query_one("#new-deck-box")
        assert box.size.width <= 40
        assert box.outer_size.height <= 12


@pytest.mark.asyncio
async def test_notice_stays_on_top_of_new_deck_wizard(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=tmp_path / "new.deck")
    async with app.run_test(size=(20, 6)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TooSmallScreen)


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(40, 12), (80, 50)])
async def test_help_panel_capped_below_the_whole_screen(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await pilot.press("?")
        await pilot.pause()
        panel = _main(app).query_one("#help-panel")
        assert panel.display is True
        assert panel.outer_size.height <= size[1] * 6 // 10
        assert _main(app).query_one("#deck-view").size.height >= 2


@pytest.mark.asyncio
async def test_notice_under_another_screen_leaves_once_it_resurfaces(
    tmp_path: Path,
) -> None:
    """A screen pushed over the notice (the new-deck prompt) hides the
    resize from it; it checks again when it is back on top."""
    from textual.screen import Screen

    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(20, 6)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TooSmallScreen)
        app.push_screen(Screen())
        await pilot.pause()
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        app.pop_screen()
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)

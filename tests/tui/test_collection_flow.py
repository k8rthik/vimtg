"""Collection flow (Textual pilot): the configured CSV loads on deck open,
a missing file warns without blocking the deck, and :collection saves
its path."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from vimtg.config.paths import config_dir
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine

_DECK = (
    "// Deck: Burn\n"
    "// Format: modern\n"
    "4 Lightning Bolt\n"
    "4 Goblin Guide\n"
    "20 Mountain\n"
    "SB: 2 Lightning Bolt\n"
)


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(_DECK, encoding="utf-8")
    return path


def _csv(tmp_path: Path) -> Path:
    path = tmp_path / "manabox.csv"
    path.write_text(
        "Name,Set code,Quantity\nLightning Bolt,sta,5\nMountain,m21,20\n",
        encoding="utf-8",
    )
    return path


def _configure(collection: str) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    (config_dir() / "config.toml").write_text(
        f'[editor]\ncollection = "{collection}"\n', encoding="utf-8"
    )


def _screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


async def _ex(pilot, text: str) -> None:  # type: ignore[no-untyped-def]
    for ch in text:
        await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_configured_collection_loads_on_deck_open(tmp_path: Path) -> None:
    _configure(str(_csv(tmp_path)))
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = _screen(app)
        collection = screen._state.collection
        assert collection is not None
        assert collection.owned_count("Lightning Bolt") == 5
        await _ex(pilot, ":collection")
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.message == "Collection: 25 cards (2 unique) from manabox.csv"


@pytest.mark.asyncio
async def test_missing_configured_file_warns_once_and_keeps_the_deck(
    tmp_path: Path,
) -> None:
    _configure(str(tmp_path / "gone.csv"))
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = _screen(app)
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.message.startswith("Collection not loaded: ")
        assert "gone.csv" in cl.message
        assert screen._state.collection is None
        start = screen._state.cursor.row
        await pilot.press("j")
        await pilot.pause()
        assert screen._state.cursor.row == start + 1


@pytest.mark.asyncio
async def test_collection_command_loads_and_persists_the_path(tmp_path: Path) -> None:
    csv_path = _csv(tmp_path)
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = _screen(app)
        assert screen._state.collection is None
        await _ex(pilot, f":collection {csv_path}")
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.message == "Collection: 25 cards (2 unique) from manabox.csv"
        assert screen._state.collection is not None
        saved = tomllib.loads((config_dir() / "config.toml").read_text(encoding="utf-8"))
        assert saved["editor"]["collection"] == str(csv_path)
        await _ex(pilot, ":collection!")
        assert cl.message == "Collection cleared"
        assert screen._state.collection is None
        saved = tomllib.loads((config_dir() / "config.toml").read_text(encoding="utf-8"))
        assert saved["editor"]["collection"] == ""


@pytest.mark.asyncio
async def test_deck_view_marks_missing_cards_and_analytics_shows_the_block(
    tmp_path: Path,
) -> None:
    from vimtg.tui.widgets.analytics_panel import AnalyticsPanel
    from vimtg.tui.widgets.deck_view import DeckView

    _configure(str(_csv(tmp_path)))
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = _screen(app)
        view = screen.query_one("#deck-view", DeckView)
        rows = view.render().plain.splitlines()
        guide = next(r for r in rows if "Goblin Guide" in r)
        bolt_side = next(r for r in rows if r.lstrip("○!✗ 0123456789").startswith("SB:"))
        mountain = next(r for r in rows if "Mountain" in r)
        assert guide.startswith("○")
        # 6 Bolts across zones: 1 is missing, but the copy-limit error wins the cell
        assert bolt_side.startswith("✗")
        assert not mountain.startswith("○")
        await _ex(pilot, ":analytics")
        panel = screen.query_one("#analytics-panel", AnalyticsPanel)
        text = panel.render().plain
        assert "COLLECTION" in text
        assert "Owned 25/30" in text
        assert "Missing 5 (2 unique)" in text

"""EDHREC pane flow with a stubbed client (Textual pilot)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from vimtg.services.edhrec import EdhrecCard, EdhrecPage, EdhrecTab
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.edhrec_panel import EdhrecPanel

_COMMANDER_DECK = (
    "// Format: commander\n"
    "\n"
    "// Commander\n"
    "CMD: 1 Atraxa, Praetors' Voice\n"
    "\n"
    "// Land\n"
    "99 Forest\n"
)

_PAGE = EdhrecPage(
    commander="Atraxa, Praetors' Voice",
    tabs=(
        EdhrecTab(
            label="Top",
            cards=(
                EdhrecCard("Sol Ring", 900, 1000, 0.0),
                EdhrecCard("Forest", 800, 1000, 0.0),
            ),
        ),
        EdhrecTab(
            label="Creatures",
            cards=(EdhrecCard("Solemn Simulacrum", 500, 1000, 0.2),),
        ),
    ),
)


class _StubClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def fetch(self, commanders: object) -> EdhrecPage:
        return _PAGE


def _deck(tmp_path: Path, text: str = _COMMANDER_DECK) -> Path:
    path = tmp_path / "edh.deck"
    path.write_text(text, encoding="utf-8")
    return path


def _main_screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


async def _open_edhrec(pilot, app: VimTGApp) -> EdhrecPanel:
    for ch in ":edhrec":
        await pilot.press(ch)
    await pilot.press("enter")
    await app.workers.wait_for_complete()
    await pilot.pause()
    return _main_screen(app).query_one("#edhrec-panel", EdhrecPanel)


@pytest.mark.asyncio
async def test_edhrec_opens_panel_with_tabs(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch("vimtg.tui.screens.main_screen.EdhrecClient", _StubClient):
        async with app.run_test() as pilot:
            screen = _main_screen(app)
            panel = await _open_edhrec(pilot, app)
            assert panel.display is True
            assert panel.page is _PAGE
            comp = screen._split_pane
            assert comp is not None
            assert comp.kind == "edhrec"
            assert comp.focused is True  # keys drive the panel immediately


@pytest.mark.asyncio
async def test_tab_and_selection_keys(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch("vimtg.tui.screens.main_screen.EdhrecClient", _StubClient):
        async with app.run_test() as pilot:
            panel = await _open_edhrec(pilot, app)
            assert panel.active_tab == 0
            await pilot.press("l")
            assert panel.active_tab == 1
            await pilot.press("h")
            assert panel.active_tab == 0
            await pilot.press("j")
            assert panel.selected == 1
            await pilot.press("k")
            assert panel.selected == 0


@pytest.mark.asyncio
async def test_enter_adds_selected_card_to_deck(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch("vimtg.tui.screens.main_screen.EdhrecClient", _StubClient):
        async with app.run_test() as pilot:
            screen = _main_screen(app)
            await _open_edhrec(pilot, app)
            assert "Sol Ring" not in screen._state.buffer.to_text()
            await pilot.press("enter")
            assert "1 Sol Ring" in screen._state.buffer.to_text()
            assert screen._state.modified is True


@pytest.mark.asyncio
async def test_enter_on_card_already_in_deck_increments(
    tmp_path: Path,
) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch("vimtg.tui.screens.main_screen.EdhrecClient", _StubClient):
        async with app.run_test() as pilot:
            screen = _main_screen(app)
            panel = await _open_edhrec(pilot, app)
            panel.select_next()  # "Forest", already in the deck
            await pilot.press("enter")
            text = screen._state.buffer.to_text()
            assert "100 Forest" in text


@pytest.mark.asyncio
async def test_deck_names_marked_for_checkmarks(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch("vimtg.tui.screens.main_screen.EdhrecClient", _StubClient):
        async with app.run_test() as pilot:
            panel = await _open_edhrec(pilot, app)
            assert "forest" in panel.deck_names
            assert "atraxa, praetors' voice" in panel.deck_names


@pytest.mark.asyncio
async def test_edhrec_requires_commander(tmp_path: Path) -> None:
    deck = _deck(tmp_path, "// Format: commander\n100 Forest\n")
    app = VimTGApp(deck_path=deck)
    with patch("vimtg.tui.screens.main_screen.EdhrecClient", _StubClient):
        async with app.run_test() as pilot:
            screen = _main_screen(app)
            for ch in ":edhrec":
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause()
            cl = screen.query_one("#command-line", CommandLine)
            assert cl.error
            assert "No commander" in cl.message
            assert screen._split_pane is None


@pytest.mark.asyncio
async def test_fetch_failure_shows_error_in_panel(tmp_path: Path) -> None:
    from vimtg.services.edhrec import EdhrecError

    class _FailingClient(_StubClient):
        def fetch(self, commanders: object) -> EdhrecPage:
            raise EdhrecError("No EDHREC page for Atraxa (HTTP 404)")

    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch("vimtg.tui.screens.main_screen.EdhrecClient", _FailingClient):
        async with app.run_test() as pilot:
            panel = await _open_edhrec(pilot, app)
            assert panel.page is None
            assert panel.status_error is True
            assert "No EDHREC page" in panel.status


@pytest.mark.asyncio
async def test_sr_key_opens_edhrec(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch("vimtg.tui.screens.main_screen.EdhrecClient", _StubClient):
        async with app.run_test() as pilot:
            screen = _main_screen(app)
            await pilot.press("S", "r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert screen._split_pane is not None
            assert screen._split_pane.kind == "edhrec"


_CATEGORY_DECK = (
    "// Format: commander\n"
    "\n"
    "CMD: 1 Atraxa, Praetors' Voice\n"
    "\n"
    "// @ramp\n"
    "1 Cultivate  @ramp\n"
    "\n"
    "// @lands\n"
    "99 Forest  @lands\n"
)


@pytest.mark.asyncio
async def test_enter_respects_category_layout(tmp_path: Path) -> None:
    """An EDHREC insert follows the same placement policy as every other
    insert: in a category-grouped deck it joins the uncategorized group
    rather than creating a type header."""
    app = VimTGApp(deck_path=_deck(tmp_path, _CATEGORY_DECK))
    with patch("vimtg.tui.screens.main_screen.EdhrecClient", _StubClient):
        async with app.run_test() as pilot:
            screen = _main_screen(app)
            await _open_edhrec(pilot, app)
            await pilot.press("enter")
            lines = screen._state.buffer.to_text().splitlines()
            assert lines[-2:] == ["// Uncategorized", "1 Sol Ring"]
            assert not any(line.startswith("// Artifact") for line in lines)

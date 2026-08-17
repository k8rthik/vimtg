"""TUI regressions from the audit: stale completion, EDHREC races."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from vimtg.services.edhrec import EdhrecCard, EdhrecPage, EdhrecTab
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.edhrec_panel import EdhrecPanel

_PAGE = EdhrecPage(
    commander="Atraxa",
    tabs=(EdhrecTab(label="Top", cards=(EdhrecCard("Sol Ring", 9, 10, 0.0),)),),
)
_STALE = EdhrecPage(
    commander="STALE",
    tabs=(EdhrecTab(label="Top", cards=(EdhrecCard("Old", 1, 10, 0.0),)),),
)


class _StubClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def fetch(self, commanders: object) -> EdhrecPage:
        return _PAGE


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "edh.deck"
    path.write_text(
        "// Format: commander\nCMD: 1 Atraxa\n99 Forest\n", encoding="utf-8"
    )
    return path


def _screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


@pytest.mark.asyncio
async def test_tab_does_not_resurrect_previous_completion(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        screen = _screen(app)
        cl = screen.query_one("#command-line", CommandLine)
        # Build a completion state for "st", abandon it
        for ch in ":st":
            await pilot.press(ch)
        await pilot.press("escape")
        # Sv prefills 'vsplit ' — Tab must not replace it with 'stats'
        await pilot.press("S", "v")
        assert cl.text == "vsplit "
        await pilot.press("tab")
        assert not cl.text.startswith("stats")
        await pilot.press("escape")
        # A fresh ':' + Tab must not accept the stale completion either
        await pilot.press(":")
        await pilot.press("tab")
        assert cl.text != "stats"


@pytest.mark.asyncio
async def test_stale_edhrec_result_is_discarded(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch("vimtg.tui.screens.main_screen.EdhrecClient", _StubClient):
        async with app.run_test() as pilot:
            screen = _screen(app)
            for ch in ":edhrec":
                await pilot.press(ch)
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            panel = screen.query_one("#edhrec-panel", EdhrecPanel)
            assert panel.page is _PAGE
            current_gen = screen._edhrec_generation
            # A result from a superseded fetch must be dropped
            screen._edhrec_loaded(_STALE, "", current_gen - 1)
            assert panel.page is _PAGE
            screen._edhrec_failed("boom", current_gen - 1)
            assert panel.status_error is False
            # The current generation still lands
            screen._edhrec_loaded(_STALE, "", current_gen)
            assert panel.page is _STALE

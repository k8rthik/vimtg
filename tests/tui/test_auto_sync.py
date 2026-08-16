"""Auto-sync gating and card-repo hot-attach on the TUI app."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.config.settings import Settings
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen


def _spy_start(app: VimTGApp, calls: list[str]) -> None:
    app._start_auto_sync = lambda: calls.append("sync")  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_env_guard_blocks_auto_sync() -> None:
    """The conftest guard (VIMTG_NO_AUTOSYNC) keeps app tests offline."""
    calls: list[str] = []
    app = VimTGApp()
    _spy_start(app, calls)
    async with app.run_test() as pilot:
        await pilot.press("escape")
    assert calls == []


@pytest.mark.asyncio
async def test_auto_sync_starts_when_no_card_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VIMTG_NO_AUTOSYNC")
    calls: list[str] = []
    app = VimTGApp()
    _spy_start(app, calls)
    async with app.run_test() as pilot:
        await pilot.press("escape")
    assert calls == ["sync"]


@pytest.mark.asyncio
async def test_setting_off_disables_auto_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VIMTG_NO_AUTOSYNC")
    calls: list[str] = []
    app = VimTGApp()
    app._settings = Settings(auto_sync_cards=False)
    _spy_start(app, calls)
    async with app.run_test() as pilot:
        await pilot.press("escape")
    assert calls == []


@pytest.mark.asyncio
async def test_finish_auto_sync_attaches_repo(tmp_path: Path) -> None:
    """After a first-run sync, the open editor gains card search/lint."""
    deck = tmp_path / "t.deck"
    deck.write_text("4 Lightning Bolt\n", encoding="utf-8")
    app = VimTGApp(deck_path=deck)
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, MainScreen)
        # Fresh XDG dirs → no card DB existed at startup
        assert screen.card_repo is None
        app._finish_auto_sync(42)
        await pilot.pause()
        assert app._card_repo is not None
        assert screen.card_repo is app._card_repo
        assert screen.search_service is app._search_svc

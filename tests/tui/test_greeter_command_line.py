"""The greeter has a small `:` command line, so `:e x.deck` opens a deck
instead of pressing the menu's e and x. It runs the editor's own
commands (same parsing, aliases and messages): :e {file}, :enew,
:q / :q!, :sync, :help [topic], with Tab completing the names. While a
card sync runs, the menu does not offer [s] Sync cards."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tui.test_greeter import _HostApp
from vimtg.tui.screens.greeter import GreeterMode, GreeterScreen, GreeterView
from vimtg.tui.screens.help_screen import HelpScreen


class _SyncHost(_HostApp):
    def __init__(self, screen: GreeterScreen) -> None:
        super().__init__(screen)
        self.syncs: list[bool] = []
        self.card_sync_running = False

    def start_card_sync(self, force: bool = False) -> str:
        self.syncs.append(force)
        return "Syncing card data in the background"


async def _command(pilot, text: str, *, submit: bool = True) -> None:  # type: ignore[no-untyped-def]
    await pilot.press("colon")
    for ch in text:
        await pilot.press({" ": "space", "!": "exclamation_mark", ".": "full_stop"}.get(ch, ch))
    if submit:
        await pilot.press("enter")
    await pilot.pause()


def _host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[_SyncHost, GreeterScreen]:
    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    return _SyncHost(screen), screen


@pytest.mark.asyncio
async def test_e_file_opens_that_deck(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "burn.deck").write_text("4 Lightning Bolt\n", encoding="utf-8")
    app, screen = _host(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _command(pilot, "e burn")
        assert app.launched == [(tmp_path / "burn.deck", None)]


@pytest.mark.asyncio
async def test_typing_a_command_never_runs_menu_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, screen = _host(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        await _command(pilot, "e x.deck", submit=False)
        assert gv._mode is GreeterMode.MENU
        assert ":e x.deck" in gv.render().plain
        await pilot.press("escape")
        await pilot.pause()
        assert app.launched == [] and not app._exit
        assert ":e x.deck" not in gv.render().plain


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["q", "q!", "quit"])
async def test_q_quits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    app, _screen = _host(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _command(pilot, command)
        assert app._exit


@pytest.mark.asyncio
async def test_enew_opens_a_new_deck(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _screen = _host(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _command(pilot, "enew")
        assert app.launched == [(None, None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(("command", "force"), [("sync", False), ("sync!", True)])
async def test_sync_starts_the_card_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, force: bool
) -> None:
    app, screen = _host(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _command(pilot, command)
        assert app.syncs == [force]
        assert screen.query_one(GreeterView)._status.startswith("Syncing card data")


@pytest.mark.asyncio
async def test_help_topic_opens_the_help_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, screen = _host(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _command(pilot, "help sort")
        assert isinstance(app.screen, HelpScreen)
        assert app.screen._topic == "sort"
        await pilot.press("q")
        await pilot.pause()
        assert app.screen is screen


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("w", "E492: Not an editor command: w"),
        ("e", "E32: No file name"),
        ("help nonsense", "E: No help for: nonsense"),
    ],
)
async def test_errors_read_as_in_the_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, message: str
) -> None:
    app, screen = _host(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _command(pilot, command)
        assert screen.query_one(GreeterView)._status == message
        assert app.launched == [] and not app._exit


@pytest.mark.asyncio
async def test_tab_completes_command_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _screen = _host(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _command(pilot, "sy", submit=False)
        await pilot.press("tab", "enter")
        await pilot.pause()
        assert app.syncs == [False]


@pytest.mark.asyncio
async def test_sync_action_hidden_while_a_sync_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, screen = _host(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        assert "Sync cards" in gv.render().plain
        app.card_sync_running = True
        screen.set_card_data_status("syncing card data downloading 10%", False)
        await pilot.pause()
        assert "Sync cards" not in gv.render().plain
        app.card_sync_running = False
        screen.set_card_data_status("card data 1 day old", False)
        assert "Sync cards" in gv.render().plain

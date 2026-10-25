"""Pilot integration tests for the VCS ex commands.

Drives :commit and :checkpoint end-to-end through MainScreen; the command
under test is always typed through the real key pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.pilot import Pilot

from vimtg.editor.buffer import Buffer
from vimtg.services.vcs_service import VersionControlService
from vimtg.tui.app import VimTGApp
from vimtg.tui.key_translator import _TEXTUAL_TO_SYMBOL
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine

_SYMBOL_TO_TEXTUAL = {v: k for k, v in _TEXTUAL_TO_SYMBOL.items()}

BASE_DECK = (
    "// Deck: Test\n// Format: modern\n\n"
    "4 Goblin Guide\n4 Monastery Swiftspear\n4 Lightning Bolt\n"
)


def _deck_file(tmp_path: Path) -> Path:
    p = tmp_path / "deck.deck"
    p.write_text(BASE_DECK, encoding="utf-8")
    return p


def _main_screen(app: VimTGApp) -> MainScreen:
    return app.screen  # type: ignore[return-value]


async def _type_command(pilot: Pilot[None], text: str) -> None:
    await pilot.press("colon")
    for ch in text:
        await pilot.press(_SYMBOL_TO_TEXTUAL.get(ch, ch))
    await pilot.press("enter")
    await pilot.pause()


def _message(scr: MainScreen) -> str:
    return scr.query_one("#command-line", CommandLine).message


def _vcs(scr: MainScreen) -> VersionControlService:
    vcs = scr._get_vcs_service()
    assert vcs is not None
    return vcs


def _set_buffer(scr: MainScreen, text: str) -> None:
    scr._state.buffer = Buffer.from_text(text)


@pytest.mark.asyncio
async def test_checkpoint_commits_and_tags(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        await _type_command(pilot, "checkpoint fnm-list")
        assert "Checkpoint: fnm-list" in _message(scr)
        log = _vcs(scr).get_log()
        assert log[0].tag == "fnm-list"


@pytest.mark.asyncio
async def test_unsaved_deck_refuses_history_until_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsaved decks used to share one '(unsaved)' history, so one new
    deck's snapshots showed up in the next."""
    from vimtg.tui.screens.new_deck import NewDeckScreen

    monkeypatch.chdir(tmp_path)
    app = VimTGApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        if isinstance(app.screen, NewDeckScreen):
            await pilot.press("escape")
            await pilot.pause()
        scr = _main_screen(app)
        assert isinstance(scr, MainScreen)
        assert scr.file_path is None
        for command in ('commit "first"', "checkpoint v1"):
            await _type_command(pilot, command)
            assert _message(scr).startswith("E32: No file name"), command
        await pilot.press("g", "h")
        await pilot.pause()
        assert app.screen is scr
        assert _message(scr).startswith("E32: No file name")


@pytest.mark.asyncio
async def test_commit_right_after_save_keeps_its_message(tmp_path: Path) -> None:
    """:w snapshots the deck as "auto: save"; the :commit that follows
    names that snapshot instead of reporting the auto one."""
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        _set_buffer(scr, BASE_DECK + "4 Lava Spike\n")
        await _type_command(pilot, "w")
        await _type_command(pilot, "commit first try")
        assert _message(scr) == "Snapshot: first try"
        await _type_command(pilot, "commit second")
        assert _message(scr) == "Nothing to commit: the deck matches snapshot 'first try'"
        assert [s.description for s in _vcs(scr).get_log()][:1] == ["first try"]


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["branch", "branch! x", "merge x", "rebase x"])
async def test_branching_commands_are_not_editor_commands(
    tmp_path: Path, command: str
) -> None:
    """Deck history is linear: the git-style branch commands are gone."""
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        await _type_command(pilot, command)
        assert _message(scr) == f"E492: Not an editor command: {command}"

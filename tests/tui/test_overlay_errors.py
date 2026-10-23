"""Errors on the history and merge command lines read and look like the
editor's: `E…:`-prefixed and drawn in the error colour, while status
messages keep their own style. The editor and history word the same
refusal the same way."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.tui.history_support import STATE_V2, HistoryHostApp, make_history_screen
from tests.tui.test_merge_screen import _HostApp as MergeHost
from tests.tui.test_merge_screen import _make_screen as make_merge_screen
from tests.tui.test_merge_screen import _Recorder
from vimtg.services.vcs_service import VersionControlService
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.history_screen import HistoryCommandLine
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.screens.merge_screen import MergeCommandLine
from vimtg.tui.theme import COLORS
from vimtg.tui.widgets.branches_panel import BranchesPanel
from vimtg.tui.widgets.command_line import CommandLine


def _drawn_in_error_colour(line: HistoryCommandLine | MergeCommandLine) -> bool:
    rendered = line.render()
    return any(COLORS["error"] in str(span.style) for span in rendered.spans)


@pytest.mark.asyncio
async def test_history_database_error_is_drawn_as_an_error(
    vcs_with_history: VersionControlService, monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(*_args: object) -> None:
        raise sqlite3.OperationalError("database is locked")

    screen = make_history_screen(vcs_with_history)
    app = HistoryHostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        monkeypatch.setattr(vcs_with_history, "create_branch", locked)
        await pilot.press("b", "x", "enter")
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert cl.message.startswith("E: Database error")
        assert _drawn_in_error_colour(cl)


@pytest.mark.asyncio
async def test_history_status_message_is_not_an_error(
    vcs_with_history: VersionControlService,
) -> None:
    screen = make_history_screen(vcs_with_history)
    app = HistoryHostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert cl.message.startswith("Detail:")
        assert not _drawn_in_error_colour(cl)


@pytest.mark.asyncio
async def test_history_duplicate_branch_is_an_error_worded_like_the_editor(
    vcs_with_history: VersionControlService,
) -> None:
    screen = make_history_screen(vcs_with_history)
    app = HistoryHostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("b", "m", "a", "i", "n", "enter")
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert cl.message == "E: Branch exists: main"
        assert _drawn_in_error_colour(cl)


@pytest.mark.asyncio
async def test_merge_unresolved_refusal_is_an_error() -> None:
    screen = make_merge_screen(_Recorder())
    app = MergeHost(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        cl = screen.query_one("#merge-command", MergeCommandLine)
        assert cl.message.startswith("E:") and "unresolved" in cl.message
        assert _drawn_in_error_colour(cl)


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "deck.deck"
    path.write_text("// Deck: Test\n\n4 Lightning Bolt\n", encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_editor_vcs_without_database_is_an_error(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, MainScreen)
        screen._db = None
        screen._vcs_service = None
        screen._execute_ex("history")
        await pilot.pause()
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.message == "E: VCS unavailable (no database)"
        assert cl.error


UNCOMMITTED_HISTORY = "E: Uncommitted changes — commit them first (c)"
UNCOMMITTED_EDITOR = "E: Uncommitted changes — commit them first (:commit)"


@pytest.mark.asyncio
async def test_history_and_editor_word_uncommitted_changes_alike(
    vcs_with_history: VersionControlService, tmp_path: Path,
) -> None:
    vcs_with_history.create_branch("budget")
    screen = make_history_screen(vcs_with_history, current_state=STATE_V2 + "1 Shock\n")
    app = HistoryHostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("2")
        branches = screen.query_one("#branches-panel", BranchesPanel)
        while (selected := branches.get_selected_branch()) and selected.name != "budget":
            await pilot.press("j")
        await pilot.press("B")
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert cl.message == UNCOMMITTED_HISTORY
        assert _drawn_in_error_colour(cl)

    editor = VimTGApp(deck_path=_deck(tmp_path))
    async with editor.run_test() as pilot:
        await pilot.pause()
        main = editor.screen
        assert isinstance(main, MainScreen)
        main._execute_ex("commit first")
        main._execute_ex("branch budget")
        main._execute_ex("1d")
        main._execute_ex("branch! budget")
        await pilot.pause()
        cl = main.query_one("#command-line", CommandLine)
        assert cl.message == UNCOMMITTED_EDITOR
        assert cl.error

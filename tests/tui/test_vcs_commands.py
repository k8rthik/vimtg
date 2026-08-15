"""Pilot integration tests for the VCS ex commands.

Drives :branch, :checkpoint, :merge, and :rebase end-to-end through
MainScreen. History setup goes through the service directly (committing
via the UI per scenario would just re-test the :commit path); the command
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
from vimtg.tui.screens.merge_screen import MergeScreen
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
async def test_branch_create_list_switch(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)

        await _type_command(pilot, "branch budget")
        assert "Nothing committed yet" in _message(scr)

        await _type_command(pilot, 'commit "initial"')
        await _type_command(pilot, "branch budget")
        assert "Branch created: budget" in _message(scr)

        await _type_command(pilot, "branch budget")
        assert "Branch exists" in _message(scr)

        await _type_command(pilot, "branch")
        assert "*main" in _message(scr)
        assert "budget" in _message(scr)

        await _type_command(pilot, "branch! budget")
        assert "Switched to branch: budget" in _message(scr)
        assert _vcs(scr).current_branch == "budget"

        await _type_command(pilot, "branch! nonexistent")
        assert "Branch not found" in _message(scr)


@pytest.mark.asyncio
async def test_branch_switch_refuses_dirty_buffer(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        await _type_command(pilot, 'commit "initial"')
        await _type_command(pilot, "branch budget")
        _set_buffer(scr, scr._state.buffer.to_text() + "2 Shock\n")
        await _type_command(pilot, "branch! budget")
        assert "Uncommitted changes" in _message(scr)
        assert _vcs(scr).current_branch == "main"


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


def _diverge(scr: MainScreen) -> VersionControlService:
    """main: base -> +Shock (buffer synced); budget: base -> +Chandra."""
    vcs = _vcs(scr)
    base = scr._state.buffer.to_text()
    vcs.commit(base, "initial")
    vcs.create_branch("budget")
    vcs.switch_branch("budget")
    vcs.commit(base + "2 Chandra, Torch of Defiance\n", "add chandra")
    vcs.switch_branch("main")
    main_state = base + "2 Shock\n"
    _set_buffer(scr, main_state)
    vcs.commit(main_state, "add shock")
    return vcs


@pytest.mark.asyncio
async def test_merge_branch_clean(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        _diverge(scr)
        await _type_command(pilot, "merge budget")
        assert "Merged budget into main" in _message(scr)
        text = scr._state.buffer.to_text()
        assert "Chandra, Torch of Defiance" in text
        assert "Shock" in text


@pytest.mark.asyncio
async def test_merge_fast_forward(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        vcs = _vcs(scr)
        base = scr._state.buffer.to_text()
        vcs.commit(base, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        vcs.commit(base + "2 Shock\n", "ahead")
        vcs.switch_branch("main")
        await _type_command(pilot, "merge budget")
        assert "Fast-forward" in _message(scr)
        assert "Shock" in scr._state.buffer.to_text()


@pytest.mark.asyncio
async def test_merge_conflict_resolves_via_screen(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        vcs = _vcs(scr)
        base = scr._state.buffer.to_text()
        vcs.commit(base, "initial")
        vcs.create_branch("budget")
        vcs.switch_branch("budget")
        vcs.commit(base.replace("4 Goblin Guide", "2 Goblin Guide"), "two")
        vcs.switch_branch("main")
        main_state = base.replace("4 Goblin Guide", "1 Goblin Guide")
        _set_buffer(scr, main_state)
        vcs.commit(main_state, "one")

        await _type_command(pilot, "merge budget")
        assert isinstance(app.screen, MergeScreen)
        await pilot.press("t")  # take theirs (2)
        await pilot.press("enter")
        await pilot.pause()
        assert "Merged budget into main" in _message(scr)
        assert "2 Goblin Guide" in scr._state.buffer.to_text()
        assert _vcs(scr).get_log()[0].merge_parent_id is not None


@pytest.mark.asyncio
async def test_merge_deck_file_by_path(tmp_path: Path) -> None:
    other = tmp_path / "other.deck"
    other.write_text("4 Lava Spike\n2 Lightning Bolt\n", encoding="utf-8")
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        await _type_command(pilot, 'commit "initial"')

        await _type_command(pilot, "merge other.deck")
        # Overlapping Lightning Bolt (4 vs 2) conflicts
        assert isinstance(app.screen, MergeScreen)
        await pilot.press("o")  # keep ours (4)
        await pilot.press("enter")
        await pilot.pause()
        text = scr._state.buffer.to_text()
        assert "Lava Spike" in text
        assert "4 Lightning Bolt" in text
        assert _vcs(scr).get_log()[0].merge_parent_id is None


@pytest.mark.asyncio
async def test_merge_unknown_target_errors(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        await _type_command(pilot, 'commit "initial"')
        await _type_command(pilot, "merge nonsense")
        assert "No branch or deck file" in _message(scr)


@pytest.mark.asyncio
async def test_merge_refuses_dirty_buffer(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        _diverge(scr)
        _set_buffer(scr, scr._state.buffer.to_text() + "1 Skewer the Critics\n")
        await _type_command(pilot, "merge budget")
        assert "Uncommitted changes" in _message(scr)


@pytest.mark.asyncio
async def test_rebase_replays_onto_target(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        vcs = _diverge(scr)
        state = vcs.switch_branch("budget")
        assert state is not None
        _set_buffer(scr, state)

        await _type_command(pilot, "rebase main")
        assert "Rebased 1 commit(s) onto main" in _message(scr)
        text = scr._state.buffer.to_text()
        assert "Chandra, Torch of Defiance" in text
        assert "Shock" in text
        log = vcs.get_log()
        assert log[0].description == "add chandra"
        assert log[1].description == "add shock"


@pytest.mark.asyncio
async def test_rebase_unknown_branch_errors(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        scr = _main_screen(app)
        await _type_command(pilot, 'commit "initial"')
        await _type_command(pilot, "rebase nonexistent")
        assert "Branch not found" in _message(scr)

"""Tests for the interactive merge conflict resolution screen."""

from __future__ import annotations

import pytest
from textual.app import App

from vimtg.domain.deck import DeckSection
from vimtg.domain.deck_merge import CardKey, MergeConflict
from vimtg.services.vcs_service import PendingMerge
from vimtg.tui.screens.merge_screen import (
    MergeCommandLine,
    MergeInputMode,
    MergeScreen,
)
from vimtg.tui.widgets.conflicts_panel import ConflictsPanel

BOLT = MergeConflict(
    card_name="Lightning Bolt",
    section=DeckSection.MAIN,
    base_quantity=4,
    ours_quantity=3,
    theirs_quantity=2,
)
SHOCK = MergeConflict(
    card_name="Shock",
    section=DeckSection.SIDEBOARD,
    base_quantity=None,
    ours_quantity=2,
    theirs_quantity=4,
)


def _pending(*conflicts: MergeConflict) -> PendingMerge:
    return PendingMerge(
        source_label="budget",
        ours_tip_id="tip1",
        theirs_tip_id="tip2",
        ours_state="3 Lightning Bolt\nSB: 2 Shock\n",
        merged={("Goblin Guide", DeckSection.MAIN): 4},
        conflicts=conflicts or (BOLT, SHOCK),
    )


class _Recorder:
    def __init__(self) -> None:
        self.completed: dict[CardKey, int | None] | None = None
        self.aborted = False

    def on_complete(self, resolutions: dict[CardKey, int | None]) -> None:
        self.completed = resolutions

    def on_abort(self) -> None:
        self.aborted = True


class _HostApp(App[None]):
    def __init__(self, screen: MergeScreen) -> None:
        super().__init__()
        self._target = screen

    def on_mount(self) -> None:
        self.push_screen(self._target)


def _make_screen(recorder: _Recorder, *conflicts: MergeConflict) -> MergeScreen:
    return MergeScreen(
        pending=_pending(*conflicts),
        deck_name="Burn",
        on_complete=recorder.on_complete,
        on_abort=recorder.on_abort,
    )


class TestMergeCommandLine:
    def test_default_hint_bar_lists_all_keys(self) -> None:
        cl = MergeCommandLine()
        text = cl.render().plain
        for hint in ("j/k", "o", "t", "c", "u", "Enter", "q"):
            assert hint in text

    def test_message_replaces_hints(self) -> None:
        cl = MergeCommandLine()
        cl.show_message("done")
        assert "done" in cl.render().plain


class TestConflictsPanel:
    def test_render_shows_quantities_and_unresolved_marker(self) -> None:
        cp = ConflictsPanel()
        cp.conflicts = (BOLT,)
        text = cp.render().plain
        assert "Lightning Bolt" in text
        assert "0/1 resolved" in text
        assert "?" in text

    def test_render_shows_resolution(self) -> None:
        cp = ConflictsPanel()
        cp.conflicts = (BOLT,)
        cp.resolutions = {BOLT.key: 3}
        text = cp.render().plain
        assert "1/1 resolved" in text

    def test_render_marks_omitted(self) -> None:
        cp = ConflictsPanel()
        cp.conflicts = (BOLT,)
        cp.resolutions = {BOLT.key: None}
        assert "omit" in cp.render().plain

    def test_sideboard_conflict_labels_section(self) -> None:
        cp = ConflictsPanel()
        cp.conflicts = (SHOCK,)
        assert "(sideboard)" in cp.render().plain


@pytest.mark.asyncio
async def test_resolve_all_and_confirm() -> None:
    recorder = _Recorder()
    screen = _make_screen(recorder)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("o")  # Bolt -> ours (3), auto-advances
        await pilot.press("t")  # Shock -> theirs (4)
        await pilot.press("enter")
        await pilot.pause()
    assert recorder.completed == {BOLT.key: 3, SHOCK.key: 4}
    assert recorder.aborted is False


@pytest.mark.asyncio
async def test_confirm_blocked_while_unresolved() -> None:
    recorder = _Recorder()
    screen = _make_screen(recorder)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("o")
        await pilot.press("enter")
        await pilot.pause()
        cl = screen.query_one("#merge-command", MergeCommandLine)
        assert "unresolved" in cl.message
    assert recorder.completed is None


@pytest.mark.asyncio
async def test_custom_quantity_flow() -> None:
    recorder = _Recorder()
    screen = _make_screen(recorder, BOLT)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        assert screen._input_mode is MergeInputMode.CUSTOM_QTY
        await pilot.press("7")
        await pilot.press("enter")
        await pilot.press("enter")  # confirm
        await pilot.pause()
    assert recorder.completed == {BOLT.key: 7}


@pytest.mark.asyncio
async def test_custom_zero_omits_card() -> None:
    recorder = _Recorder()
    screen = _make_screen(recorder, BOLT)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.press("0")
        await pilot.press("enter")
        await pilot.press("enter")
        await pilot.pause()
    assert recorder.completed == {BOLT.key: None}


@pytest.mark.asyncio
async def test_unresolve_clears_choice() -> None:
    recorder = _Recorder()
    screen = _make_screen(recorder, BOLT)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("o")
        cp = screen.query_one("#conflicts-panel", ConflictsPanel)
        assert cp.resolutions == {BOLT.key: 3}
        await pilot.press("u")
        assert cp.resolutions == {}
    assert recorder.completed is None


@pytest.mark.asyncio
async def test_abort_calls_on_abort() -> None:
    recorder = _Recorder()
    screen = _make_screen(recorder)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("o")
        await pilot.press("q")
        await pilot.pause()
    assert recorder.aborted is True
    assert recorder.completed is None


@pytest.mark.asyncio
async def test_ours_none_side_resolves_to_omit() -> None:
    delete_conflict = MergeConflict(
        card_name="Shock",
        section=DeckSection.MAIN,
        base_quantity=2,
        ours_quantity=None,  # we deleted it
        theirs_quantity=3,
    )
    recorder = _Recorder()
    screen = _make_screen(recorder, delete_conflict)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("o")
        await pilot.press("enter")
        await pilot.pause()
    assert recorder.completed == {delete_conflict.key: None}

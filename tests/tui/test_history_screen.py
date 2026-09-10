"""Tests for the lazygit-style HistoryScreen.

Combines fast unit tests for the two embedded Static widgets (command line and
status line) with pilot-driven integration tests that exercise the real key
path: commit, branch, tag/untag, restore confirmation, and navigation.
"""

from __future__ import annotations

import pytest

from tests.tui.history_support import (
    STATE_V1,
    STATE_V2,
    HistoryHostApp,
    make_history_screen,
)
from vimtg.services.vcs_service import VersionControlService
from vimtg.tui.screens.history_screen import (
    HistoryCommandLine,
    HistoryScreen,
    HistoryStatusLine,
    InputMode,
    Panel,
)
from vimtg.tui.widgets.branches_panel import BranchesPanel
from vimtg.tui.widgets.diff_panel import DiffPanel
from vimtg.tui.widgets.snapshots_panel import SnapshotsPanel

# ──────────────────────────────────────────────────────────────────
# Unit tests: HistoryCommandLine
# ──────────────────────────────────────────────────────────────────


class TestHistoryCommandLine:
    def test_default_hint_bar(self) -> None:
        cl = HistoryCommandLine()
        text = cl.render().plain
        assert "ommit" in text
        assert "ranch" in text
        assert "back" in text

    def test_show_message(self) -> None:
        cl = HistoryCommandLine()
        cl.show_message("Saved")
        assert cl.message == "Saved"
        assert cl.prompt == ""
        assert "Saved" in cl.render().plain

    def test_show_prompt_resets_text(self) -> None:
        cl = HistoryCommandLine()
        cl.text = "leftover"
        cl.show_prompt("Commit message: ")
        assert cl.prompt == "Commit message: "
        assert cl.text == ""
        assert cl.cursor_pos == 0

    def test_render_prompt_with_cursor_at_end(self) -> None:
        cl = HistoryCommandLine()
        cl.show_prompt("Name: ")
        cl.text = "abc"
        cl.cursor_pos = 3
        rendered = cl.render().plain
        assert "Name: " in rendered
        assert "abc" in rendered

    def test_render_prompt_with_cursor_mid_text(self) -> None:
        cl = HistoryCommandLine()
        cl.show_prompt("Name: ")
        cl.text = "abc"
        cl.cursor_pos = 1
        # Cursor is rendered as a reverse-styled char; plain text is preserved.
        assert "abc" in cl.render().plain

    def test_hide_clears_all(self) -> None:
        cl = HistoryCommandLine()
        cl.show_prompt("x")
        cl.text = "y"
        cl.cursor_pos = 1
        cl.hide()
        assert cl.prompt == ""
        assert cl.text == ""
        assert cl.message == ""
        assert cl.cursor_pos == 0


# ──────────────────────────────────────────────────────────────────
# Unit tests: HistoryStatusLine
# ──────────────────────────────────────────────────────────────────


class TestHistoryStatusLine:
    def test_render_shows_deck_and_branch(self) -> None:
        sl = HistoryStatusLine()
        sl.deck_name = "Burn"
        sl.branch = "main"
        sl.snapshot_count = 3
        sl.active_panel = Panel.SNAPSHOTS
        rendered = sl.render().plain
        assert "HISTORY" in rendered
        assert "Burn" in rendered
        assert "[main]" in rendered
        assert "3 snapshots" in rendered
        assert "Snapshots" in rendered


# ──────────────────────────────────────────────────────────────────
# Integration tests: HistoryScreen via pilot
# ──────────────────────────────────────────────────────────────────


_HostApp = HistoryHostApp
_make_screen = make_history_screen


@pytest.mark.asyncio
async def test_mount_populates_panels(vcs_with_history: VersionControlService) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
        bp = screen.query_one("#branches-panel", BranchesPanel)
        sl = screen.query_one("#history-status", HistoryStatusLine)
        assert len(sp.snapshots) == 2
        assert len(bp.branches) == 1
        assert sl.snapshot_count == 2


@pytest.mark.asyncio
async def test_diff_populated_for_selected(
    vcs_with_history: VersionControlService,
) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        dp = screen.query_one("#diff-panel", DiffPanel)
        assert dp.diff is not None  # tip snapshot has a parent → real diff


@pytest.mark.asyncio
async def test_tab_cycles_panels(vcs_with_history: VersionControlService) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert screen._active_panel == Panel.SNAPSHOTS
        await pilot.press("tab")
        assert screen._active_panel == Panel.DIFF
        await pilot.press("shift+tab")
        assert screen._active_panel == Panel.SNAPSHOTS


@pytest.mark.asyncio
async def test_navigation_updates_selection(
    vcs_with_history: VersionControlService,
) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
        assert sp.selected == 0
        await pilot.press("j")
        assert sp.selected == 1
        await pilot.press("k")
        assert sp.selected == 0


@pytest.mark.asyncio
async def test_commit_flow_creates_snapshot(
    vcs_with_history: VersionControlService,
) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        assert screen._input_mode == InputMode.COMMIT
        for ch in "tune":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
        assert len(sp.snapshots) == 3
        assert screen._input_mode == InputMode.NORMAL


@pytest.mark.asyncio
async def test_commit_empty_description_cancelled(
    vcs_with_history: VersionControlService,
) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.press("enter")  # no text
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert "Cancelled" in cl.message
        sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
        assert len(sp.snapshots) == 2


@pytest.mark.asyncio
async def test_escape_cancels_input_mode(
    vcs_with_history: VersionControlService,
) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        for ch in "abc":
            await pilot.press(ch)
        await pilot.press("escape")
        assert screen._input_mode == InputMode.NORMAL
        assert screen._input_text == ""


@pytest.mark.asyncio
async def test_backspace_edits_input(
    vcs_with_history: VersionControlService,
) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("b")
        for ch in "abc":
            await pilot.press(ch)
        await pilot.press("backspace")
        assert screen._input_text == "ab"


@pytest.mark.asyncio
async def test_branch_flow_creates_branch(
    vcs_with_history: VersionControlService,
) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("b")
        for ch in "budget":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        bp = screen.query_one("#branches-panel", BranchesPanel)
        names = {b.name for b in bp.branches}
        assert "budget" in names


@pytest.mark.asyncio
async def test_branch_duplicate_reports_error(
    vcs_with_history: VersionControlService,
) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("b")
        for ch in "main":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert "already exists" in cl.message


@pytest.mark.asyncio
async def test_tag_and_untag_flow(vcs_with_history: VersionControlService) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        assert screen._input_mode == InputMode.TAG
        for ch in "gp":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
        assert sp.snapshots[0].tag == "gp"
        # Untag the same snapshot
        await pilot.press("T")
        await pilot.pause()
        sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
        assert sp.snapshots[0].tag is None


@pytest.mark.asyncio
async def test_restore_confirm_yes_calls_callback(
    vcs_with_history: VersionControlService,
) -> None:
    restored: list[str] = []
    screen = _make_screen(vcs_with_history, on_restore=restored.append)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("R")
        assert screen._input_mode == InputMode.CONFIRM_RESTORE
        await pilot.press("y")
        await pilot.press("enter")
        await pilot.pause()
        assert len(restored) == 1
        assert restored[0] == STATE_V2  # tip snapshot state


@pytest.mark.asyncio
async def test_restore_confirm_no_cancels(
    vcs_with_history: VersionControlService,
) -> None:
    restored: list[str] = []
    screen = _make_screen(vcs_with_history, on_restore=restored.append)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("R")
        await pilot.press("n")
        await pilot.press("enter")
        await pilot.pause()
        assert restored == []
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert "cancelled" in cl.message.lower()


@pytest.mark.asyncio
async def test_toggle_detail(vcs_with_history: VersionControlService) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        dp = screen.query_one("#diff-panel", DiffPanel)
        before = dp.show_unchanged
        await pilot.press("d")
        assert dp.show_unchanged is not before


@pytest.mark.asyncio
async def test_q_pops_screen(vcs_with_history: VersionControlService) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, HistoryScreen)
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, HistoryScreen)


@pytest.mark.asyncio
async def test_branch_empty_name_cancelled(
    vcs_with_history: VersionControlService,
) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("b")
        await pilot.press("enter")  # empty
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert "Cancelled" in cl.message


@pytest.mark.asyncio
async def test_tag_empty_cancelled(vcs_with_history: VersionControlService) -> None:
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        await pilot.press("enter")  # empty
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert "Cancelled" in cl.message


@pytest.mark.asyncio
async def test_restore_with_no_snapshot_is_noop(vcs: VersionControlService) -> None:
    screen = _make_screen(vcs)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("R")
        assert screen._input_mode == InputMode.NORMAL


@pytest.mark.asyncio
async def test_tag_with_no_snapshot_is_noop(vcs: VersionControlService) -> None:
    # Empty history → no selected snapshot, pressing 't' should not enter TAG mode.
    screen = _make_screen(vcs)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        assert screen._input_mode == InputMode.NORMAL


@pytest.mark.asyncio
async def test_switch_branch_via_shortcut(
    vcs_with_history: VersionControlService,
) -> None:
    vcs_with_history.create_branch("budget")
    # Switching needs a clean working copy, and a branch other than the
    # current one (main): budget sorts first.
    screen = _make_screen(vcs_with_history, current_state=STATE_V2)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Move focus to the branches panel; the first branch is selected.
        await pilot.press("tab")  # SNAPSHOTS -> DIFF
        while screen._active_panel != Panel.BRANCHES:
            await pilot.press("tab")
        bp = screen.query_one("#branches-panel", BranchesPanel)
        target = bp.branches[0].name
        assert target != vcs_with_history.current_branch
        await pilot.press("B")
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert target in cl.message


@pytest.mark.asyncio
async def test_switch_branch_via_enter_on_branches(
    vcs_with_history: VersionControlService,
) -> None:
    vcs_with_history.create_branch("budget")
    screen = _make_screen(vcs_with_history, current_state=STATE_V2)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        while screen._active_panel != Panel.BRANCHES:
            await pilot.press("tab")
        await pilot.press("enter")
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert "Switched to" in cl.message


@pytest.mark.asyncio
async def test_branches_panel_navigation(
    vcs_with_history: VersionControlService,
) -> None:
    vcs_with_history.create_branch("budget")
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        while screen._active_panel != Panel.BRANCHES:
            await pilot.press("tab")
        bp = screen.query_one("#branches-panel", BranchesPanel)
        assert bp.selected == 0
        await pilot.press("j")
        assert bp.selected == 1
        await pilot.press("k")
        assert bp.selected == 0


@pytest.mark.asyncio
async def test_cherry_pick_on_branch(
    vcs_with_history: VersionControlService,
) -> None:
    # Create a second branch, switch to it, then cherry-pick a snapshot.
    vcs_with_history.create_branch("budget")
    screen = _make_screen(vcs_with_history)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert cl.message != ""

# ──────────────────────────────────────────────────────────────────
# Integration tests: merge and rebase from the history screen
# ──────────────────────────────────────────────────────────────────

STATE_CHANDRA = STATE_V1 + "2 Chandra, Torch of Defiance\n"


@pytest.fixture
def vcs_diverged(vcs: VersionControlService) -> VersionControlService:
    """main: V1 -> V2; budget (from V1): +Chandra. Current branch: main."""
    vcs.commit(STATE_V1, "initial build")
    vcs.create_branch("budget")
    vcs.switch_branch("budget")
    vcs.commit(STATE_CHANDRA, "add chandra")
    vcs.switch_branch("main")
    vcs.commit(STATE_V2, "add swiftspear")
    return vcs


@pytest.mark.asyncio
async def test_merge_key_merges_selected_branch(
    vcs_diverged: VersionControlService,
) -> None:
    restored: list[str] = []
    screen = _make_screen(
        vcs_diverged, on_restore=restored.append, current_state=STATE_V2
    )
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Branches are sorted: budget first — already selected at index 0
        await pilot.press("2", "m")
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert "Merged budget" in cl.message
        sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
        assert sp.snapshots[0].merge_parent_id is not None
    assert restored  # editor buffer got the merged state
    assert "Chandra, Torch of Defiance" in restored[-1]
    assert "Monastery Swiftspear" in restored[-1]


@pytest.mark.asyncio
async def test_merge_key_refuses_dirty_state(
    vcs_diverged: VersionControlService,
) -> None:
    screen = _make_screen(
        vcs_diverged, current_state=STATE_V2 + "1 Shock\n"
    )
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("2", "m")
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert "Uncommitted changes" in cl.message


@pytest.mark.asyncio
async def test_merge_key_refuses_current_branch(
    vcs_with_history: VersionControlService,
) -> None:
    screen = _make_screen(vcs_with_history, current_state=STATE_V2)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("2", "m")  # only branch is main == current
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert "Already on that branch" in cl.message


@pytest.mark.asyncio
async def test_merge_with_conflicts_pushes_merge_screen(
    vcs: VersionControlService,
) -> None:
    from vimtg.tui.screens.merge_screen import MergeScreen

    vcs.commit(STATE_V1, "initial")
    vcs.create_branch("budget")
    vcs.switch_branch("budget")
    vcs.commit("2 Lightning Bolt\n4 Goblin Guide\n", "trim bolts")
    vcs.switch_branch("main")
    vcs.commit("1 Lightning Bolt\n4 Goblin Guide\n", "one bolt")
    screen = _make_screen(
        vcs, current_state="1 Lightning Bolt\n4 Goblin Guide\n"
    )
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("2", "m")
        await pilot.pause()
        assert isinstance(app.screen, MergeScreen)


@pytest.mark.asyncio
async def test_rebase_key_confirms_then_rebases(
    vcs_diverged: VersionControlService,
) -> None:
    restored: list[str] = []
    vcs_diverged.switch_branch("budget")
    screen = _make_screen(
        vcs_diverged, on_restore=restored.append, current_state=STATE_CHANDRA
    )
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        bp = screen.query_one("#branches-panel", BranchesPanel)
        bp.select_next()  # budget, main -> select main
        await pilot.press("2", "r")
        assert screen._input_mode == InputMode.CONFIRM_REBASE
        await pilot.press("y")
        await pilot.press("enter")
        await pilot.pause()
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert "Rebased 1 commit" in cl.message
        sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
        assert sp.snapshots[0].description == "add chandra"
        assert sp.snapshots[1].description == "add swiftspear"
    assert restored
    assert "Monastery Swiftspear" in restored[-1]


@pytest.mark.asyncio
async def test_rebase_cancelled_with_n(
    vcs_diverged: VersionControlService,
) -> None:
    vcs_diverged.switch_branch("budget")
    screen = _make_screen(vcs_diverged, current_state=STATE_CHANDRA)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        bp = screen.query_one("#branches-panel", BranchesPanel)
        bp.select_next()
        await pilot.press("2", "r")
        await pilot.press("n")
        await pilot.press("enter")
        cl = screen.query_one("#history-command", HistoryCommandLine)
        assert "cancelled" in cl.message.lower()
        sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
        assert sp.snapshots[0].description == "add chandra"
        assert len(sp.snapshots) == 2


@pytest.mark.asyncio
async def test_hint_bar_lists_merge_and_rebase() -> None:
    cl = HistoryCommandLine()
    text = cl.render().plain
    assert "merge" in text
    assert "rebase" in text


@pytest.mark.asyncio
async def test_merge_commit_renders_marker(
    vcs_diverged: VersionControlService,
) -> None:
    vcs_diverged.merge_branch("budget")
    screen = _make_screen(vcs_diverged, current_state=STATE_V2)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
        assert "⇄ merge" in sp.render().plain

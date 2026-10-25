"""The history screen is a floating lazygit-style overlay.

Opens over the editor as a modal, closes on q / Escape / gh, jumps panels
with 1-4, scrolls the diff, shows the working copy, and restores a
snapshot into the editor.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.screen import ModalScreen

from tests.tui.history_support import (
    STATE_V1,
    STATE_V2,
    HistoryHostApp,
    make_history_screen,
)
from vimtg.domain.deck_diff import ChangeType
from vimtg.services.deck_diff_service import DeckDiffService
from vimtg.services.vcs_service import VersionControlService
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.history_screen import (
    HistoryCommandLine,
    HistoryScreen,
    HistoryStatusLine,
    InputMode,
    Panel,
)
from vimtg.tui.widgets.diff_panel import DiffPanel
from vimtg.tui.widgets.snapshots_panel import SnapshotsPanel
from vimtg.tui.widgets.stats_panel import StatsPanel
from vimtg.tui.widgets.working_copy_panel import WorkingCopyPanel

_HostApp = HistoryHostApp
_screen = make_history_screen


def _cl(screen: HistoryScreen) -> HistoryCommandLine:
    return screen.query_one("#history-command", HistoryCommandLine)


def _many(n: int, prefix: str) -> str:
    return "".join(f"1 {prefix} {i}\n" for i in range(n))


# ── Overlay shape ─────────────────────────────────────────────────


class TestOverlayShape:
    def test_is_a_modal_screen(self, vcs_with_history: VersionControlService) -> None:
        assert isinstance(_screen(vcs_with_history), ModalScreen)

    @pytest.mark.asyncio
    async def test_floating_window_has_title(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            window = screen.query_one("#history-window")
            assert "Burn" in str(window.border_title)
            assert "gh" in str(window.border_subtitle)

    @pytest.mark.asyncio
    async def test_layout_fits_an_80x24_terminal(
        self, vcs_with_history: VersionControlService
    ) -> None:
        tip = vcs_with_history.get_log()[0]
        vcs_with_history.tag(tip.id, "regional-championship-qualifier")
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            window = screen.query_one("#history-window")
            assert 0 < window.size.width < 80 and 0 < window.size.height < 24
            status = screen.query_one("#history-status", HistoryStatusLine)
            command = _cl(screen)
            # both bottom bars are visible on their own rows
            assert status.region.y != command.region.y
            assert status.region.height == 1 and command.region.height == 1
            # no rendered row wraps: rules, entries, and the working-copy line
            for panel_id in ("#working-panel", "#snapshots-panel",
                             "#diff-panel", "#stats-panel"):
                panel = screen.query_one(panel_id)
                for row in panel.render().plain.split("\n"):
                    assert len(row) <= panel.size.width, (panel_id, row)
            # the snapshot window is derived from the real height
            sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
            assert sp.max_visible * 2 + 2 <= sp.size.height

    @pytest.mark.asyncio
    async def test_hint_bar_compacts_when_narrow(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        async with _HostApp(screen).run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            plain = _cl(screen).render().plain
            assert len(plain) <= _cl(screen).size.width
            assert plain.lstrip().startswith("q")
            assert "d" in plain.split()  # last action key still shown
        wide = _screen(vcs_with_history)
        async with _HostApp(wide).run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            plain = _cl(wide).render().plain
            assert "q/Esc back" in plain and "? help" in plain


# ── Close keys and pending g ──────────────────────────────────────


class TestClose:
    @pytest.mark.parametrize("keys", [("escape",), ("g", "h")])
    @pytest.mark.asyncio
    async def test_close_keys_pop_overlay(
        self, vcs_with_history: VersionControlService, keys: tuple[str, ...]
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            depth = len(app.screen_stack)
            await pilot.press(*keys)
            await pilot.pause()
            assert len(app.screen_stack) == depth - 1

    @pytest.mark.asyncio
    async def test_escape_in_prompt_only_cancels_prompt(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            depth = len(app.screen_stack)
            await pilot.press("c", "x", "escape")
            await pilot.pause()
            assert len(app.screen_stack) == depth
            assert _cl(screen).prompt == ""

    @pytest.mark.asyncio
    async def test_pending_g_shows_indicator_and_falls_through(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("g")
            assert _cl(screen).pending == "g"
            assert "g-" in _cl(screen).render().plain
            await pilot.press("1")
            assert _cl(screen).pending == ""
            assert screen._active_panel is Panel.WORKING
            depth = len(app.screen_stack)
            await pilot.press("g", "q")
            await pilot.pause()
            assert len(app.screen_stack) == depth - 1

    @pytest.mark.asyncio
    async def test_gg_goes_to_top_not_close(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            depth = len(app.screen_stack)
            sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
            await pilot.press("j")
            assert sp.selected == 1
            await pilot.press("g", "g")
            assert sp.selected == 0
            await pilot.press("G")
            assert sp.selected == 1
            assert len(app.screen_stack) == depth


# ── Opening from the editor ───────────────────────────────────────


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(
        "// Deck: Burn\n// Format: modern\n\nDCK:\n    4 Lightning Bolt\n", encoding="utf-8"
    )
    return path


class TestOpenFromEditor:
    @pytest.mark.asyncio
    async def test_gh_opens_overlay_end_to_end(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            editor = app.screen
            await pilot.press("g", "h")
            await pilot.pause()
            assert isinstance(app.screen, HistoryScreen)
            await pilot.press("g", "h")
            await pilot.pause()
            assert app.screen is editor

    @pytest.mark.asyncio
    async def test_history_command_opens_overlay(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press(":", *"history", "enter")
            await pilot.pause()
            assert isinstance(app.screen, HistoryScreen)

    @pytest.mark.asyncio
    async def test_restore_keeps_cursor_row_and_closes(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            editor = app.screen
            vcs = editor._get_vcs_service()  # type: ignore[attr-defined]
            state = editor._state  # type: ignore[attr-defined]
            base = state.buffer.to_text()
            vcs.commit(base, "base")
            vcs.commit(base + "    4 Shock\n", "add shock")
            await pilot.press("G")
            row_before = state.cursor.row
            assert row_before > 0
            await pilot.press("g", "h", "j", "R", "y", "enter")
            await pilot.pause()
            assert app.screen is editor
            assert "Shock" not in state.buffer.to_text()
            assert state.cursor.row == min(row_before, state.buffer.line_count() - 1)


# ── Panel jumps ───────────────────────────────────────────────────


class TestPanelJumps:
    @pytest.mark.asyncio
    async def test_number_keys_jump_to_panels(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            for key, panel in (
                ("1", Panel.WORKING), ("2", Panel.SNAPSHOTS),
                ("3", Panel.DIFF), ("4", Panel.STATS),
            ):
                await pilot.press(key)
                assert screen._active_panel is panel

    @pytest.mark.asyncio
    async def test_tab_order_keeps_snapshots_then_diff(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert screen._active_panel is Panel.SNAPSHOTS
            await pilot.press("tab")
            assert screen._active_panel is Panel.DIFF
            await pilot.press("shift+tab")
            assert screen._active_panel is Panel.SNAPSHOTS
            await pilot.press("shift+tab")
            assert screen._active_panel is Panel.WORKING

    @pytest.mark.asyncio
    async def test_enter_on_snapshot_opens_diff(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            assert screen._active_panel is Panel.DIFF

    @pytest.mark.asyncio
    async def test_snapshot_actions_only_in_snapshots_panel(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            for key in ("t", "T", "R"):
                await pilot.press("1", key)
                assert "Snapshots panel" in _cl(screen).message, key
                assert screen._input_mode is InputMode.NORMAL


# ── Working copy ──────────────────────────────────────────────────


class TestWorkingCopy:
    @pytest.mark.asyncio
    async def test_dirty_working_copy_shows_counts(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            wp = screen.query_one("#working-panel", WorkingCopyPanel)
            assert wp.dirty is True
            assert wp.diff is not None and wp.diff.added_count == 1

    @pytest.mark.asyncio
    async def test_metadata_change_is_dirty(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history, current_state="// Format: modern\n" + STATE_V2)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            wp = screen.query_one("#working-panel", WorkingCopyPanel)
            assert wp.dirty is vcs_with_history.is_dirty("// Format: modern\n" + STATE_V2)
            if wp.dirty:
                assert "metadata or plans" in wp.render().plain

    @pytest.mark.asyncio
    async def test_selecting_working_panel_shows_working_diff(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            dp = screen.query_one("#diff-panel", DiffPanel)
            await pilot.press("1")
            assert dp.diff is not None
            names = {c.card_name for c in dp.diff.changes if c.new_quantity}
            assert "Shock" in names
            await pilot.press("2")
            assert dp.diff is not None
            names = {c.card_name for c in dp.diff.changes}
            assert "Shock" not in names

    @pytest.mark.asyncio
    async def test_commit_cleans_working_copy(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            wp = screen.query_one("#working-panel", WorkingCopyPanel)
            await pilot.press("c")
            for ch in "add shock":
                await pilot.press(ch if ch != " " else "space")
            await pilot.press("enter")
            await pilot.pause()
            assert wp.dirty is False
            assert "clean" in wp.render().plain

    @pytest.mark.asyncio
    async def test_no_snapshots_yet(self, vcs: VersionControlService) -> None:
        screen = _screen(vcs)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            wp = screen.query_one("#working-panel", WorkingCopyPanel)
            assert wp.has_tip is False


# ── Restore ──────────────────────────────────────────────────────


class TestRestore:
    @pytest.mark.asyncio
    async def test_restore_calls_back_and_closes(
        self, vcs_with_history: VersionControlService
    ) -> None:
        restored: list[str] = []
        screen = _screen(vcs_with_history, on_restore=restored.append)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            depth = len(app.screen_stack)
            await pilot.press("j", "R", "y", "enter")
            await pilot.pause()
            assert restored == [STATE_V1]
            assert len(app.screen_stack) == depth - 1

    @pytest.mark.asyncio
    async def test_restore_without_handler_reports(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history, on_restore=None)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("R", "y", "enter")
            assert "unavailable" in _cl(screen).message.lower()


# ── Scrolling the diff and stats ──────────────────────────────────


class TestDiffScroll:
    @pytest.mark.asyncio
    async def test_keys_scroll_diff_when_focused(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(_many(30, "Card"), "big")
        vcs.commit(_many(30, "Card") + _many(30, "New"), "bigger")
        screen = _screen(vcs, current_state=_many(30, "Card") + _many(30, "New"))
        app = _HostApp(screen)
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause()
            dp = screen.query_one("#diff-panel", DiffPanel)
            assert dp.max_scroll > 0
            await pilot.press("3", "j", "j")
            assert dp.scroll_pos == 2
            await pilot.press("k")
            assert dp.scroll_pos == 1
            await pilot.press("G")
            assert dp.scroll_pos == dp.max_scroll
            await pilot.press("g", "g")
            assert dp.scroll_pos == 0
            await pilot.press("ctrl+d")
            assert dp.scroll_pos > 0
            await pilot.press("ctrl+u")
            assert dp.scroll_pos == 0

    @pytest.mark.asyncio
    async def test_panel_switch_keeps_diff_scroll(
        self, vcs: VersionControlService
    ) -> None:
        vcs.commit(_many(30, "Card"), "big")
        vcs.commit(_many(30, "Card") + _many(30, "New"), "bigger")
        screen = _screen(vcs, current_state=_many(30, "Card") + _many(30, "New"))
        app = _HostApp(screen)
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause()
            dp = screen.query_one("#diff-panel", DiffPanel)
            await pilot.press("3", "j", "j", "j")
            assert dp.scroll_pos == 3
            await pilot.press("4", "3", "tab", "shift+tab")
            assert dp.scroll_pos == 3
            # a different snapshot is a new diff: back to the top
            await pilot.press("2", "j", "3")
            assert dp.scroll_pos == 0

    @pytest.mark.asyncio
    async def test_wheel_over_snapshots_follows_selection(
        self, vcs: VersionControlService
    ) -> None:
        for i in range(30):
            vcs.commit(_many(i + 1, "Card"), f"commit {i}")
        screen = _screen(vcs, current_state=_many(30, "Card"))
        app = _HostApp(screen)
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause()
            sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
            dp = screen.query_one("#diff-panel", DiffPanel)
            for _ in range(6):
                sp.wheel(1)
            await pilot.pause()
            assert sp.scroll_pos == 6 and sp.selected == 6
            assert dp.diff is not None
            added = {c.card_name for c in dp.diff.changes if c.change_type is ChangeType.ADDED}
            assert added == {"Card 23"}

    @pytest.mark.asyncio
    async def test_resize_keeps_selection_visible(
        self, vcs: VersionControlService
    ) -> None:
        for i in range(30):
            vcs.commit(_many(i + 1, "Card"), f"commit {i}")
        screen = _screen(vcs, current_state=_many(30, "Card"))
        app = _HostApp(screen)
        async with app.run_test(size=(120, 50)) as pilot:
            await pilot.pause()
            sp = screen.query_one("#snapshots-panel", SnapshotsPanel)
            for _ in range(12):
                await pilot.press("j")
            assert sp.selected == 12 and sp.scroll_pos == 0
            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            assert sp.scroll_pos <= sp.selected < sp.scroll_pos + sp.max_visible

    @pytest.mark.asyncio
    async def test_stats_panel_gets_currency(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history, price_source="eur")
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert screen.query_one("#stats-panel", StatsPanel).currency == "€"

    @pytest.mark.asyncio
    async def test_no_card_data_placeholder(
        self, vcs_with_history: VersionControlService
    ) -> None:
        screen = _screen(vcs_with_history)  # DeckDiffService() has no card repo
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            plain = screen.query_one("#stats-panel", StatsPanel).render().plain
            assert "vimtg sync" in plain

    @pytest.mark.asyncio
    async def test_diffs_are_priced_in_the_configured_source(
        self, vcs_with_history: VersionControlService
    ) -> None:
        class _Recording(DeckDiffService):
            sources: list[str] = []

            def diff_snapshot_parent(  # type: ignore[override]
                self, deck_state: str, parent_state: str | None, price_source: str = "usd"
            ):
                self.sources.append(price_source)
                return super().diff_snapshot_parent(deck_state, parent_state, price_source)

        svc = _Recording()
        screen = _screen(vcs_with_history, price_source="eur", diff_service=svc)
        app = _HostApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("1", "2")
            assert svc.sources and set(svc.sources) == {"eur"}


# ── Hint bar stays in sync with the keys ──────────────────────────


class TestHintCoverage:
    def test_every_action_key_is_hinted(self) -> None:
        from vimtg.tui.screens.history_screen import _ACTIONS, _HINTS

        hinted = {part for key, _ in _HINTS for part in key.split("/")}
        missing = [k for k in _ACTIONS if k not in hinted]
        assert missing == []

    def test_every_action_method_exists(self) -> None:
        from vimtg.tui.screens.history_screen import _ACTIONS

        for method in _ACTIONS.values():
            assert callable(getattr(HistoryScreen, method))

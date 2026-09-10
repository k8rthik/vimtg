"""Cross-screen key consistency: the shared vocabulary works everywhere,
and the audit's bugs stay fixed."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App

from vimtg.config.settings import Settings
from vimtg.editor.keymap import KeyMap, KeyResult
from vimtg.editor.modes import Mode
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.config_screen import ConfigScreen, ConfigView
from vimtg.tui.screens.greeter import GreeterMode, GreeterScreen, GreeterView
from vimtg.tui.screens.help_screen import HelpScreen
from vimtg.tui.screens.history_screen import HistoryScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.help_panel import HelpPanel


def _deck(tmp_path: Path, n: int = 40) -> Path:
    path = tmp_path / "big.deck"
    body = "".join(f"    1 Card {i}\n" for i in range(n))
    path.write_text("// Deck: Big\n// Format: modern\n\nDCK:\n" + body)
    return path


# ── Editor bugs from the audit ────────────────────────────────────


class TestEditorFixes:
    @pytest.mark.asyncio
    async def test_search_typing_is_visible(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("slash", *"card 3")
            cl = app.screen.query_one("#command-line", CommandLine)
            assert cl.text == "card 3"
            await pilot.press("enter")
            await pilot.pause()
            state = app.screen._state  # type: ignore[attr-defined]
            assert "Card 3" in state.buffer.get_line(state.cursor.row).text

    def test_register_prefix_rejects_punctuation(self) -> None:
        km = KeyMap(mode=Mode.NORMAL)
        km.feed('"')
        result, _ = km.feed(":")
        assert result == KeyResult.NO_MATCH
        km.feed('"')
        assert km.feed("a")[0] == KeyResult.PENDING
        km.feed('"')
        assert km.feed("1")[0] == KeyResult.PENDING

    @pytest.mark.asyncio
    async def test_1g_goes_to_line_one(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            state = app.screen._state  # type: ignore[attr-defined]
            await pilot.press("G")
            assert state.cursor.row > 0
            await pilot.press("1", "G")
            assert state.cursor.row == 0
            await pilot.press("5", "G")
            assert state.cursor.row == 4


# ── Split panes share the vocabulary ──────────────────────────────


class TestPaneNavigation:
    @pytest.mark.asyncio
    async def test_deck_pane_gg_home_end(self, tmp_path: Path) -> None:
        deck = _deck(tmp_path)
        app = VimTGApp(deck_path=deck)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = app.screen
            await pilot.press(*f":vsplit {deck}", "enter")
            await pilot.pause()
            await pilot.press("S", "s")  # focus the pane
            pane = screen._split_pane  # type: ignore[attr-defined]
            assert pane is not None and pane.focused
            await pilot.press("G")
            assert pane.cursor_row == pane.buffer.line_count() - 1
            await pilot.press("g", "g")
            assert pane.cursor_row == 0
            await pilot.press("end")
            assert pane.cursor_row == pane.buffer.line_count() - 1
            await pilot.press("home")
            assert pane.cursor_row == 0
            await pilot.press("ctrl+d")
            assert pane.cursor_row > 0
            # bare g then a non-nav key: the pane is unfocused and the key runs
            await pilot.press("g", "escape")
            assert not pane.focused


# ── Help ──────────────────────────────────────────────────────────


class TestHelpKeys:
    @pytest.mark.asyncio
    async def test_help_screen_closes_on_question_mark_and_scrolls_with_gg(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause()
            await pilot.press("f1")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            scroll = app.screen.query_one("#help-scroll")
            await pilot.press("end")
            await pilot.pause()
            assert scroll.scroll_offset.y > 0
            await pilot.press("home")
            await pilot.pause()
            assert scroll.scroll_offset.y == 0
            await pilot.press("question_mark")
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen)

    @pytest.mark.asyncio
    async def test_help_panel_home_end(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            hp = app.screen.query_one("#help-panel", HelpPanel)
            await pilot.press("end")
            await pilot.pause()
            assert hp.scroll_offset.y > 0
            await pilot.press("home")
            await pilot.pause()
            assert hp.scroll_offset.y == 0


# ── Greeter ───────────────────────────────────────────────────────


class _GreeterHost(App[None]):
    def __init__(self, files: list[Path]) -> None:
        super().__init__()
        self._files = files
        self.launched: list[object] = []

    def on_mount(self) -> None:
        self.push_screen(GreeterScreen(recent_files=self._files))

    def open_deck(self, *args: object, **kwargs: object) -> None:  # duck-typed nav
        self.launched.append((args, kwargs))


class TestGreeterKeys:
    @pytest.mark.asyncio
    async def test_escape_on_menu_does_not_quit(self, tmp_path: Path) -> None:
        app = _GreeterHost([])
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert not app._exit  # still running
            gv = app.screen.query_one(GreeterView)
            assert gv._mode is GreeterMode.MENU

    @pytest.mark.asyncio
    async def test_f1_opens_help_and_lists_use_shared_keys(self, tmp_path: Path) -> None:
        files = []
        for i in range(12):
            f = tmp_path / f"d{i:02d}.deck"
            f.write_text("// Deck: x\n")
            files.append(f)
        app = _GreeterHost(files)
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            gv = app.screen.query_one(GreeterView)
            await pilot.press("f1")
            assert gv._mode is GreeterMode.HELP
            await pilot.press("ctrl+d")
            assert gv._help_offset > 0
            await pilot.press("g", "g")
            assert gv._help_offset == 0
            await pilot.press("escape")
            assert gv._mode is GreeterMode.MENU
            await pilot.press("r")
            assert gv._mode is GreeterMode.RECENT
            await pilot.press("G")
            assert gv._cursor == len(gv._recent) - 1
            await pilot.press("home")
            assert gv._cursor == 0
            await pilot.press("ctrl+d")
            assert gv._cursor > 0
            gv.wheel_test = None  # noqa: B010 - attribute only for clarity
            await pilot.press("down", "up")
            assert gv._cursor > 0


# ── Config ────────────────────────────────────────────────────────


class _ConfigHost(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.saved: list[Settings] = []

    def on_mount(self) -> None:
        self.push_screen(ConfigScreen(Settings(), on_save=self.saved.append))


class TestConfigKeys:
    @pytest.mark.asyncio
    async def test_ctrl_c_respects_the_discard_guard(self) -> None:
        app = _ConfigHost()
        async with app.run_test() as pilot:
            await pilot.pause()
            view = app.screen.query_one("#config-view", ConfigView)
            await pilot.press("l")  # change a value
            assert view.unsaved
            depth = len(app.screen_stack)
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert len(app.screen_stack) == depth
            assert "Unsaved" in view.warning
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert len(app.screen_stack) == depth - 1

    @pytest.mark.asyncio
    async def test_shared_navigation_and_help(self) -> None:
        app = _ConfigHost()
        async with app.run_test() as pilot:
            await pilot.pause()
            view = app.screen.query_one("#config-view", ConfigView)
            await pilot.press("G")
            assert view.selected_index > 0
            await pilot.press("g", "g")
            assert view.selected_index == 0
            await pilot.press("ctrl+d")
            assert view.selected_index > 0
            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            assert app.screen._topic == "config"


# ── History overlay ───────────────────────────────────────────────


class TestHistoryKeys:
    @pytest.mark.asyncio
    async def test_help_and_snapshot_action_gating(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path, 5))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("g", "h")
            await pilot.pause()
            overlay = app.screen
            assert isinstance(overlay, HistoryScreen)
            await pilot.press("2", "t")
            assert "Snapshots panel" in overlay._cl.message
            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("q")
            await pilot.pause()
            assert app.screen is overlay
            await pilot.press("home", "end")  # accepted, no error
            await pilot.press("g", "h")
            await pilot.pause()
            assert not isinstance(app.screen, HistoryScreen)

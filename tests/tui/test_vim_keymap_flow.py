"""The vim keymap pass, driven key by key through MainScreen: window
keys on Ctrl-W, the Space leader, linewise S/C/D/Y, Ctrl-C as Esc, the
jumplist and the other vim-fidelity keys."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tui.test_vim_fidelity_flow import _cards, _deck, _feed, _message, _screen
from vimtg.tui.app import VimTGApp
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.which_key import WhichKey

SIZE = (100, 30)


class TestWhichKeyFollowsTheSequence:
    @pytest.mark.asyncio
    async def test_operator_then_g_shows_the_operator_menu(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "dg")
            plain = scr.query_one("#which-key", WhichKey).render().plain
            assert "dd" in plain and "dG" in plain
            assert "set category" not in plain


def _other(tmp_path: Path) -> Path:
    path = tmp_path / "other.deck"
    path.write_text("4 Opt\n4 Consider\n")
    return path


class TestCtrlWWindows:
    @pytest.mark.asyncio
    async def test_ctrl_w_v_and_s_prompt_for_a_deck(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<C-w>v")
            assert scr.query_one("#command-line", CommandLine).text == "vsplit "
            _feed(scr, "<Esc><C-w>s")
            assert scr.query_one("#command-line", CommandLine).text == "split "

    @pytest.mark.asyncio
    async def test_focus_moves_by_w_and_by_direction(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, f":vsplit {_other(tmp_path)}<CR>")
            pane = scr._split_pane
            assert pane is not None and not pane.focused
            _feed(scr, "<C-w>w")
            assert pane.focused
            _feed(scr, "<C-w>W")
            assert not pane.focused
            _feed(scr, "<C-w>l")
            assert pane.focused
            _feed(scr, "<C-w>j")  # nothing below a side-by-side pane
            assert pane.focused
            _feed(scr, "<C-w>h")
            assert not pane.focused

    @pytest.mark.asyncio
    async def test_a_stacked_pane_is_below(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, f":split {_other(tmp_path)}<CR><C-w>j")
            pane = scr._split_pane
            assert pane is not None and pane.focused
            _feed(scr, "<C-w>k")
            assert not pane.focused

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["c", "q", "o"])
    async def test_close_keys_close_the_pane_from_either_window(
        self, tmp_path: Path, key: str
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            other = _other(tmp_path)
            _feed(scr, f":vsplit {other}<CR><C-w>{key}")
            assert scr._split_pane is None
            _feed(scr, f":vsplit {other}<CR><C-w>w<C-w>{key}")
            assert scr._split_pane is None
            assert app.is_running

    @pytest.mark.asyncio
    async def test_without_a_pane(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<C-w>c")
            assert "E444" in _message(scr)
            _feed(scr, "<C-w>o")
            assert _message(scr) == "Already only one window"
            _feed(scr, "6Gdd<C-w>q")  # Ctrl-W q is :quit, which guards changes
            assert app.is_running
            assert "Unsaved changes" in _message(scr)

    @pytest.mark.asyncio
    async def test_which_key_titles_the_window_menu(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<C-w>")
            plain = scr.query_one("#which-key", WhichKey).render().plain
            assert "window:" in plain and "vertical split" in plain


class TestSpaceLeader:
    @pytest.mark.asyncio
    async def test_space_a_toggles_the_analytics_pane(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<Space>a")
            assert scr._split_pane is not None and scr._split_pane.kind == "analytics"
            _feed(scr, "<Space>a")
            assert scr._split_pane is None

    @pytest.mark.asyncio
    async def test_space_a_closes_it_from_the_focused_pane(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<Space>a<C-w>w")
            assert scr._split_pane is not None and scr._split_pane.focused
            _feed(scr, "<Space>a")
            assert scr._split_pane is None

    @pytest.mark.asyncio
    async def test_space_r_toggles_edhrec(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VIMTG_NO_EDHREC", "1")
        deck = _deck(tmp_path, "// Format: commander\nCMD: 1 Krenko, Mob Boss\n")
        app = VimTGApp(deck_path=deck)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<Space>r")
            assert scr._split_pane is not None and scr._split_pane.kind == "edhrec"
            _feed(scr, "<Space>r")
            assert scr._split_pane is None

    @pytest.mark.asyncio
    async def test_space_r_replaces_another_pane(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VIMTG_NO_EDHREC", "1")
        deck = _deck(tmp_path, "// Format: commander\nCMD: 1 Krenko, Mob Boss\n")
        app = VimTGApp(deck_path=deck)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<Space>a<Space>r")
            assert scr._split_pane is not None and scr._split_pane.kind == "edhrec"

    @pytest.mark.asyncio
    async def test_space_h_opens_the_hand(self, tmp_path: Path) -> None:
        from vimtg.tui.screens.hand_screen import HandScreen

        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            _feed(_screen(app), "<Space>h")
            await pilot.pause()
            assert isinstance(app.screen, HandScreen)

    @pytest.mark.asyncio
    async def test_which_key_titles_the_leader_menu(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<Space>")
            plain = scr.query_one("#which-key", WhichKey).render().plain
            assert "leader:" in plain and "analytics" in plain


class TestFocusedPaneKeys:
    @pytest.mark.asyncio
    async def test_q_closes_the_pane_without_recording(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, f":vsplit {_other(tmp_path)}<CR><C-w>w q")
            assert scr._split_pane is None
            assert not scr._state.macros.is_recording

    @pytest.mark.asyncio
    async def test_esc_returns_to_the_editor_and_keeps_the_pane(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, f":vsplit {_other(tmp_path)}<CR><C-w>w<Esc>")
            assert scr._split_pane is not None and not scr._split_pane.focused

    @pytest.mark.asyncio
    async def test_g_keys_reach_the_editor(self, tmp_path: Path) -> None:
        from vimtg.tui.widgets.help_panel import HelpPanel

        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, f":vsplit {_other(tmp_path)}<CR><C-w>w g?")
            assert scr.query_one("#help-panel", HelpPanel).display
            _feed(scr, "<Esc><C-w>w 6G gc")
            assert scr._state.tag_input_action == "category"

    @pytest.mark.asyncio
    async def test_gh_in_the_edhrec_pane_is_history_not_a_tab(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.tui.test_edhrec_flow import _PAGE
        from vimtg.tui.widgets.edhrec_panel import EdhrecPanel

        monkeypatch.setenv("VIMTG_NO_EDHREC", "1")
        deck = _deck(tmp_path, "// Format: commander\nCMD: 1 Krenko, Mob Boss\n")
        app = VimTGApp(deck_path=deck)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            opened: list[bool] = []
            scr._open_history = lambda: opened.append(True)  # type: ignore[method-assign]
            _feed(scr, "<Space>r")
            panel = scr.query_one("#edhrec-panel", EdhrecPanel)
            panel.page = _PAGE
            _feed(scr, "gh")
            assert opened == [True]
            assert panel.active_tab == 0

    @pytest.mark.asyncio
    async def test_pane_hints_name_q_and_esc(self, tmp_path: Path) -> None:
        from vimtg.tui.widgets.analytics_panel import AnalyticsPanel

        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<Space>a<C-w>w")
            plain = scr.query_one("#analytics-panel", AnalyticsPanel).render().plain
            assert "q close" in plain and "Esc editor" in plain


class TestLinewiseCapitals:
    @pytest.mark.asyncio
    async def test_d_deletes_lines_and_repeats(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G D")
            assert _cards(scr)[0] == "4 Monastery Swiftspear"
            _feed(scr, ".")
            assert _cards(scr)[0] == "2 Eidolon of the Great Revel"
            _feed(scr, "u u 6G 2D")
            assert _cards(scr)[0] == "2 Eidolon of the Great Revel"

    @pytest.mark.asyncio
    async def test_y_yanks_into_a_register(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, '11G "aY 6G "ap')
            assert _cards(scr)[:2] == ["4 Goblin Guide", "4 Lightning Bolt"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["S", "C"])
    async def test_s_and_c_change_the_line(self, tmp_path: Path, key: str) -> None:
        from vimtg.editor.modes import Mode

        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, f"6G {key}")
            assert scr._state.mode_mgr.current == Mode.INSERT
            assert "4 Goblin Guide" not in _cards(scr)

    @pytest.mark.asyncio
    async def test_visual_d_deletes_the_selection(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G Vj D")
            assert _cards(scr)[0] == "2 Eidolon of the Great Revel"

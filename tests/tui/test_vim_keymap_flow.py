"""The vim keymap pass, driven key by key through MainScreen: window
keys on Ctrl-W, the Space leader, linewise S/C/D/Y, Ctrl-C as Esc, the
jumplist and the other vim-fidelity keys."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.tui.test_vim_fidelity_flow import (
    DECK,
    FIXTURES,
    _cards,
    _deck,
    _feed,
    _message,
    _screen,
)
from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card
from vimtg.editor.modes import Mode
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.deck_view import DeckView
from vimtg.tui.widgets.which_key import WhichKey

SIZE = (100, 30)


@pytest.fixture
def card_repo(db_factory):  # type: ignore[no-untyped-def]
    repo = CardRepository(db_factory())
    data = json.loads((FIXTURES / "scryfall_sample.json").read_text(encoding="utf-8"))
    repo.bulk_insert([Card.from_scryfall(d) for d in data])
    return repo


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


class TestCtrlWWindows:
    @pytest.mark.asyncio
    async def test_w_moves_focus_into_the_pane_and_back(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<Space>a")
            pane = scr._split_pane
            assert pane is not None and not pane.focused
            _feed(scr, "<C-w>w")
            assert pane.focused
            _feed(scr, "<C-w>w")
            assert not pane.focused

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["v", "s", "W", "h", "j", "k", "l", "c", "q", "o"])
    async def test_second_deck_window_keys_are_gone(self, tmp_path: Path, key: str) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, f"<Space>a<C-w>{key}")
            pane = scr._split_pane
            assert pane is not None and not pane.focused  # the key did nothing
            assert scr._state.mode_mgr.current == Mode.NORMAL
            assert app.is_running

    @pytest.mark.asyncio
    async def test_without_a_pane(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<C-w>w")
            assert _message(scr) == "E: No pane open (Space a or Space r)"

    @pytest.mark.asyncio
    async def test_which_key_titles_the_window_menu(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<C-w>")
            plain = scr.query_one("#which-key", WhichKey).render().plain
            assert "window:" in plain and "other window" in plain


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
            _feed(scr, "<Space>a<C-w>w q")
            assert scr._split_pane is None
            assert not scr._state.macros.is_recording

    @pytest.mark.asyncio
    async def test_esc_returns_to_the_editor_and_keeps_the_pane(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<Space>a<C-w>w<Esc>")
            assert scr._split_pane is not None and not scr._split_pane.focused

    @pytest.mark.asyncio
    async def test_g_keys_reach_the_editor(self, tmp_path: Path) -> None:
        from vimtg.tui.widgets.help_panel import HelpPanel

        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<Space>a<C-w>w g?")
            assert scr.query_one("#help-panel", HelpPanel).display
            _feed(scr, "<Esc><C-w>w 6G gc")
            assert scr._state.prompt_action == "category"

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


EXIT_HINT = "Type :q and press Enter to exit vimtg"


class TestCtrlCIsEsc:
    @pytest.mark.asyncio
    async def test_idle_ctrl_c_hints_at_q_and_keeps_running(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert app.is_running
            assert _message(scr) == EXIT_HINT

    @pytest.mark.asyncio
    async def test_ctrl_c_cancels_what_esc_cancels(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            await pilot.press("2", "d", "ctrl+c")
            assert not scr.keymap.awaiting_more_keys
            assert _message(scr) != EXIT_HINT
            lines = len(_cards(scr))
            for opener in (["colon", "w"], ["V", "j"], ["o", "b"], ["slash", "x"]):
                await pilot.press("6", "G", *opener, "ctrl+c")
                assert scr._state.mode_mgr.current == Mode.NORMAL, opener
            assert len(_cards(scr)) == lines  # o's scratch line went too
            assert app.is_running

    @pytest.mark.asyncio
    async def test_ctrl_c_returns_from_a_focused_pane(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<Space>a<C-w>w")
            await pilot.press("ctrl+c")
            assert scr._split_pane is not None and not scr._split_pane.focused

    @pytest.mark.asyncio
    async def test_ctrl_c_closes_auxiliary_screens(self, tmp_path: Path) -> None:
        from vimtg.tui.screens.help_screen import HelpScreen

        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await pilot.press("f1")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("ctrl+c")
            await pilot.pause()
            _screen(app)
            assert app.is_running

    @pytest.mark.asyncio
    async def test_greeter_ctrl_c_hints_instead_of_quitting(self) -> None:
        from vimtg.tui.screens.greeter import GreeterView

        app = VimTGApp()
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert app.is_running
            assert "Press q (or type :q) to exit vimtg" in str(
                app.screen.query_one(GreeterView).render()
            )

    @pytest.mark.asyncio
    async def test_a_recovery_copy_is_not_called_a_crash(self, tmp_path: Path) -> None:
        from vimtg.services.recovery import write_recovery

        deck = _deck(tmp_path)
        write_recovery(deck, deck.read_text(encoding="utf-8") + "4 Shock\n")
        app = VimTGApp(deck_path=deck)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            message = _message(_screen(app))
            assert ":recover" in message
            assert "crash" not in message


class TestCtrlACtrlX:
    @pytest.mark.asyncio
    async def test_counts_dot_and_visual(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G 3<C-a>")
            assert _cards(scr)[0] == "7 Goblin Guide"
            _feed(scr, ". <C-x>")
            assert _cards(scr)[0] == "9 Goblin Guide"
            _feed(scr, "Vj<C-x>")
            assert _cards(scr)[:2] == ["8 Goblin Guide", "3 Monastery Swiftspear"]


def _deck_view_text(scr: MainScreen) -> str:
    return scr.query_one("#deck-view", DeckView).render().plain


class TestKShowsCardDetails:
    @pytest.mark.asyncio
    async def test_k_expands_the_cursor_card_when_autoexpand_is_off(
        self, tmp_path: Path, card_repo: CardRepository
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            scr.attach_card_repo(card_repo, scr.search_service)  # type: ignore[arg-type]
            scr._state.settings = replace(scr._state.settings, auto_expand=False)
            _feed(scr, "6G")
            assert "Goblin Scout" not in _deck_view_text(scr)
            _feed(scr, "K")
            assert "Goblin Scout" in _deck_view_text(scr)
            _feed(scr, "K")
            assert "Goblin Scout" not in _deck_view_text(scr)
            _feed(scr, "K j k")  # moving away ends it, as vim's K popup
            assert "Goblin Scout" not in _deck_view_text(scr)

    @pytest.mark.asyncio
    async def test_k_collapses_it_when_autoexpand_is_on(
        self, tmp_path: Path, card_repo: CardRepository
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            scr.attach_card_repo(card_repo, scr.search_service)  # type: ignore[arg-type]
            _feed(scr, "6G")
            assert "Goblin Scout" in _deck_view_text(scr)
            _feed(scr, "K")
            assert "Goblin Scout" not in _deck_view_text(scr)

    @pytest.mark.asyncio
    async def test_k_off_a_card_says_so(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "5G K")
            assert "E348" in _message(scr)


class TestReselectAndRepeatEx:
    @pytest.mark.asyncio
    async def test_gv_reselects_the_last_selection(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "gv")
            assert scr._state.mode_mgr.current == Mode.NORMAL
            assert "No previous visual selection" in _message(scr)
            _feed(scr, "6G Vj <Esc> 12G gv")
            assert scr._state.mode_mgr.current == Mode.VISUAL_LINE
            assert scr._state.cursor.row == 6
            _feed(scr, "d")
            assert _cards(scr)[0] == "2 Eidolon of the Great Revel"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("way_out", "end_row"), [
        ("gc core<CR>", 6), (":<Esc>", 6), ("i<Esc>", 6),
        # a search is a motion: as in vim it extends the selection to the match
        ("/Mountain<CR>", 15),
    ])
    async def test_gv_after_any_way_out_of_visual(
        self, tmp_path: Path, way_out: str, end_row: int,
    ) -> None:
        """However the selection ended, gv brings the same one back."""
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, f"6G Vj {way_out}")
            assert scr._state.mode_mgr.current == Mode.NORMAL
            _feed(scr, "12G gv")
            assert scr._state.mode_mgr.current == Mode.VISUAL_LINE
            assert (scr._state.visual_anchor, scr._state.cursor.row) == (5, end_row)

    @pytest.mark.asyncio
    async def test_gv_after_an_operator(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "11G vj y G gv")
            assert scr._state.mode_mgr.current == Mode.VISUAL
            assert scr._state.visual_anchor == 10 and scr._state.cursor.row == 11

    @pytest.mark.asyncio
    async def test_at_colon_repeats_the_last_ex_command(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "@:")
            assert "E30" in _message(scr)
            _feed(scr, "6G :.g/./d<CR> @:")
            assert _cards(scr)[0] == "2 Eidolon of the Great Revel"
            _feed(scr, "10G @@")
            assert "4 Searing Blaze" not in _cards(scr)
            _feed(scr, "9G 2@:")
            assert _cards(scr) == ["2 Eidolon of the Great Revel", "20 Mountain"]


def _row(scr: MainScreen) -> int:
    return scr._state.cursor.row + 1  # 1-based, as G counts


class TestJumplist:
    @pytest.mark.asyncio
    async def test_ctrl_o_and_ctrl_i_walk_the_jumps(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G G 11G j")  # j is not a jump
            assert _row(scr) == 12
            _feed(scr, "<C-o>")
            assert _row(scr) == 16
            _feed(scr, "<C-o>")
            assert _row(scr) == 6
            _feed(scr, "<Tab>")  # terminals send Tab for Ctrl-I
            assert _row(scr) == 16
            _feed(scr, "<Tab>")
            assert _row(scr) == 12
            _feed(scr, "2<C-o>")
            assert _row(scr) == 6

    @pytest.mark.asyncio
    async def test_quote_quote_goes_back_and_forth(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G j G")
            _feed(scr, "''")
            assert _row(scr) == 7
            _feed(scr, "''")
            assert _row(scr) == 16

    @pytest.mark.asyncio
    @pytest.mark.parametrize("jump", [
        "gg", ":16<CR>", "/Bolt<CR>", "?Bolt<CR>", "*", "#", "}", "{", "]]", "[[",
        "16G ma 7G 'a", "L", "H", "M",
    ])
    async def test_vim_jumps_are_recorded(self, tmp_path: Path, jump: str) -> None:
        # A second Swiftspear gives * and # somewhere to go
        app = VimTGApp(deck_path=_deck(tmp_path, DECK + "\nSB: 2 Monastery Swiftspear\n"))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "7G")
            _feed(scr, jump)
            assert _row(scr) != 7, jump
            _feed(scr, "<C-o>")
            assert _row(scr) in (7, 16), jump  # 'a: G was the jump before it

    @pytest.mark.asyncio
    async def test_motions_and_edits_nearby_are_not_jumps(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G j j w b + -")
            assert scr._state.jumps.rows == (0,)  # only 6G left line 1

    @pytest.mark.asyncio
    async def test_a_card_filed_far_away_is_a_jump(
        self, tmp_path: Path, card_repo: CardRepository
    ) -> None:
        from tests.tui.test_vim_fidelity_flow import _pick

        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            scr.attach_card_repo(card_repo, scr.search_service)  # type: ignore[arg-type]
            _feed(scr, "16G o")
            _pick(scr, card_repo, "Goblin Guide")  # joins the line under // Creature
            assert _row(scr) == 6
            _feed(scr, "<C-o>")
            assert _row(scr) == 16


class TestQuitClosesWindows:
    @pytest.mark.asyncio
    async def test_q_closes_the_pane_then_quits(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "<Space>a:q<CR>")
            assert scr._split_pane is None and app.is_running
            _feed(scr, "<Space>a<C-w>w:q<CR>")
            assert scr._split_pane is None and app.is_running
            _feed(scr, ":q<CR>")
            await pilot.pause()
            assert not app.is_running


class TestVisualPut:
    @pytest.mark.asyncio
    async def test_p_replaces_the_selection_and_keeps_what_it_replaced(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G yy 12G Vj p")
            assert scr._state.mode_mgr.current == Mode.NORMAL
            assert _cards(scr)[3:] == ["4 Lightning Bolt", "4 Goblin Guide", "20 Mountain"]
            assert scr._state.registers.get('"').content == (
                "4 Searing Blaze", "4 Skullcrack",
            )
            _feed(scr, "u")
            assert "4 Searing Blaze" in _cards(scr)  # one undo step

    @pytest.mark.asyncio
    async def test_capital_p_leaves_the_register_alone(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, '6G "ayy 11G V "aP')
            assert _cards(scr)[3] == "4 Goblin Guide"
            assert "4 Lightning Bolt" not in _cards(scr)
            _feed(scr, "12G V P")  # unnamed still holds Goblin Guide
            assert _cards(scr)[4] == "4 Goblin Guide"

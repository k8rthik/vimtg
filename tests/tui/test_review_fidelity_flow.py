"""Vim fidelity regressions from the pre-1.0 correctness review, driven
key by key through MainScreen. Line numbers refer to the sample deck in
test_vim_fidelity_flow (1-based, as G counts them)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tui.test_vim_fidelity_flow import _cards, _deck, _feed, _screen
from vimtg.editor.modes import Mode
from vimtg.tui.app import VimTGApp


class TestLeavingVisualEndsSelection:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("leave", ["i<CR>", "i<Esc>", "/Skull<CR>", "/x<Esc>"])
    async def test_next_dd_deletes_one_line(self, tmp_path: Path, leave: str) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, f"6G Vjj {leave}")
            assert scr._state.mode_mgr.current == Mode.NORMAL
            before = len(_cards(scr))
            _feed(scr, "dd")
            assert len(_cards(scr)) == before - 1

    @pytest.mark.asyncio
    async def test_category_prompt_from_visual_still_labels_the_selection(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G Vj gc burn<CR>")
            labelled = [c for c in _cards(scr) if "@burn" in c]
            assert len(labelled) == 2


class TestCountedX:
    @pytest.mark.asyncio
    async def test_3x_is_one_change_with_every_card_in_the_register(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            before = _cards(scr)
            _feed(scr, "11G 3x")
            assert "4 Lightning Bolt" not in _cards(scr)
            assert "4 Skullcrack" not in _cards(scr)
            assert scr._state.registers.unnamed.content == (
                "4 Lightning Bolt", "4 Searing Blaze", "4 Skullcrack",
            )
            _feed(scr, "u")
            assert _cards(scr) == before
            _feed(scr, "11G 2x .")
            assert "20 Mountain" in _cards(scr)
            assert "4 Lightning Bolt" not in _cards(scr)
            assert "4 Skullcrack" not in _cards(scr)
            _feed(scr, "u")
            assert "4 Skullcrack" in _cards(scr)
            assert "4 Lightning Bolt" not in _cards(scr)


class TestUppercaseMacroRegister:
    @pytest.mark.asyncio
    async def test_uppercase_q_appends_to_macro_a(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G qa + q qA j q")
            assert scr._state.macros.get("a").keys == ("+", "j")
            _feed(scr, "6G @a")
            assert _cards(scr)[:2] == ["6 Goblin Guide", "4 Monastery Swiftspear"]
            assert scr._state.cursor.row == 6
            _feed(scr, "@A")
            assert _cards(scr)[1] == "5 Monastery Swiftspear"


class TestQuantityUndo:
    @pytest.mark.asyncio
    async def test_bursts_on_different_cards_are_separate_changes(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G ++ j +")
            assert _cards(scr)[:2] == ["6 Goblin Guide", "5 Monastery Swiftspear"]
            _feed(scr, "u")
            assert _cards(scr)[:2] == ["6 Goblin Guide", "4 Monastery Swiftspear"]
            _feed(scr, "u")
            assert _cards(scr)[:2] == ["4 Goblin Guide", "4 Monastery Swiftspear"]

    @pytest.mark.asyncio
    async def test_undo_and_redo_move_to_the_changed_line(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "13G + G u")
            assert scr._state.cursor.row == 12
            _feed(scr, "gg")
            scr._process_key("ctrl_r")
            assert scr._state.cursor.row == 12
            _feed(scr, "6G dd G u")
            assert scr._state.cursor.row == 5


class TestMappingsMatchAtCommandStart:
    """Vim matches a mapping only where a command starts, never as the
    second key of a sequence."""

    @pytest.mark.asyncio
    async def test_mapped_s_leaves_zs_alone(self, tmp_path: Path) -> None:
        deck = _deck(tmp_path)
        app = VimTGApp(deck_path=deck)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, ":map<Space>s<Space>:w<CR> 6G zs")
            assert _cards(scr)[-1] == "    4 Goblin Guide"
            assert "SB:" not in deck.read_text(encoding="utf-8")
            _feed(scr, "s")
            assert "SB:\n    4 Goblin Guide" in deck.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_mapped_key_is_not_a_register_name(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, ':map<Space>a<Space>dd<CR> 6G "ayy')
            assert scr._state.registers.get("a").content == ("4 Goblin Guide",)

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
    async def test_tag_prompt_from_visual_still_tags_the_selection(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, "6G Vj ta burn<CR>")
            tagged = [c for c in _cards(scr) if "#burn" in c]
            assert len(tagged) == 2

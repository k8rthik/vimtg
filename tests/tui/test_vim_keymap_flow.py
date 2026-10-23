"""The vim keymap pass, driven key by key through MainScreen: window
keys on Ctrl-W, the Space leader, linewise S/C/D/Y, Ctrl-C as Esc, the
jumplist and the other vim-fidelity keys."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tui.test_vim_fidelity_flow import _deck, _feed, _screen
from vimtg.tui.app import VimTGApp
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

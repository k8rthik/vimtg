"""Tests for the inline help panel: content rendering and scrolling.

The panel is docked at the bottom with a capped height, so its ~100
lines of reference must scroll — with the same keys the full-screen
help uses — or everything past the first page is unreachable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.widgets.help_panel import HelpPanel, render_help_overview
from vimtg.tui.widgets.scrolling import scroll_step_for_key


class TestRenderHelpOverview:
    def test_header_present(self) -> None:
        plain = render_help_overview().plain
        assert "Help" in plain
        assert "? or Esc" in plain

    def test_help_content_not_empty(self) -> None:
        plain = render_help_overview().plain
        assert len(plain.split("\n")) > 5

    def test_scroll_hint_present(self) -> None:
        assert "j/k" in render_help_overview().plain


class TestScrollStepForKey:
    def test_line_keys(self) -> None:
        assert scroll_step_for_key("j", 20) == 1
        assert scroll_step_for_key("down", 20) == 1
        assert scroll_step_for_key("k", 20) == -1
        assert scroll_step_for_key("up", 20) == -1

    def test_half_page_keys(self) -> None:
        assert scroll_step_for_key("ctrl_d", 20) == 10
        assert scroll_step_for_key("ctrl_u", 20) == -10

    def test_half_page_never_zero(self) -> None:
        # A 1-row viewport must still move
        assert scroll_step_for_key("ctrl_d", 1) == 1
        assert scroll_step_for_key("ctrl_u", 1) == -1

    def test_top_and_bottom(self) -> None:
        # bare g is never a scroll key; gg is parsed by tui.keys.VimNav
        assert scroll_step_for_key("g", 20) is None
        assert scroll_step_for_key("home", 20) == "home"
        assert scroll_step_for_key("G", 20) == "end"
        assert scroll_step_for_key("end", 20) == "end"

    def test_unknown_key_is_none(self) -> None:
        assert scroll_step_for_key("x", 20) is None


def _deck_file(tmp_path: Path) -> Path:
    p = tmp_path / "deck.deck"
    p.write_text("// Creatures\n4 Goblin Guide\n", encoding="utf-8")
    return p


@pytest.mark.asyncio
async def test_j_k_scroll_help_panel(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        hp = app.screen.query_one("#help-panel", HelpPanel)
        assert hp.display is True
        assert hp.scroll_offset.y == 0
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()
        assert hp.scroll_offset.y > 0
        after_j = hp.scroll_offset.y
        await pilot.press("k")
        await pilot.pause()
        assert hp.scroll_offset.y < after_j


@pytest.mark.asyncio
async def test_top_bottom_and_half_page_scroll_help_panel(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        hp = app.screen.query_one("#help-panel", HelpPanel)
        await pilot.press("G")
        await pilot.pause()
        bottom = hp.scroll_offset.y
        assert bottom > 0
        await pilot.press("g", "g")
        await pilot.pause()
        assert hp.scroll_offset.y == 0
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert 0 < hp.scroll_offset.y < bottom
        await pilot.press("ctrl+u")
        await pilot.pause()
        assert hp.scroll_offset.y == 0


@pytest.mark.asyncio
async def test_scroll_keys_do_not_leak_to_editor(tmp_path: Path) -> None:
    """While the panel is open, j/k scroll it — the deck cursor stays put."""
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        scr = app.screen
        before = scr._state.cursor.row  # type: ignore[attr-defined]
        await pilot.press("question_mark")
        await pilot.press("j")
        await pilot.pause()
        assert scr._state.cursor.row == before  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_reopen_starts_at_top(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck_file(tmp_path))
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        hp = app.screen.query_one("#help-panel", HelpPanel)
        await pilot.press("question_mark")
        await pilot.press("G")
        await pilot.pause()
        assert hp.scroll_offset.y > 0
        await pilot.press("escape")
        await pilot.pause()
        assert hp.display is False
        await pilot.press("question_mark")
        await pilot.pause()
        assert hp.scroll_offset.y == 0

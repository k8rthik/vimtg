"""Pilot-based integration tests for the full-screen HelpScreen.

Exercises the real key path: `:help` / F1 open the screen, q/escape close it,
j/k scroll, and `:help <topic>` renders per-command help.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.help_screen import HelpScreen


async def _type_command(pilot, text: str) -> None:
    """Type an ex command character-by-character and submit it."""
    await pilot.press("colon")
    for ch in text:
        await pilot.press("space" if ch == " " else ch)
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_help_command_opens_help_screen(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _type_command(pilot, "help")
        assert isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_help_screen_shows_overview(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _type_command(pilot, "help")
        body = app.screen.query_one("#help-body")
        text = body.render()
        assert "NAVIGATION" in text.plain
        assert "vimtg Help" in text.plain


@pytest.mark.asyncio
async def test_f1_opens_help_screen(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_q_closes_help_screen(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_escape_closes_help_screen(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_j_k_scroll_help_screen(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        scroll = app.screen.query_one("#help-scroll")
        assert scroll.scroll_offset.y == 0
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause()
        assert scroll.scroll_offset.y > 0
        offset_after_j = scroll.scroll_offset.y
        await pilot.press("k")
        await pilot.pause()
        assert scroll.scroll_offset.y < offset_after_j


@pytest.mark.asyncio
async def test_g_jumps_top_and_bottom(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        scroll = app.screen.query_one("#help-scroll")
        await pilot.press("G")  # jump to bottom
        await pilot.pause()
        assert scroll.scroll_offset.y > 0
        await pilot.press("g")  # jump to top
        await pilot.pause()
        assert scroll.scroll_offset.y == 0


@pytest.mark.asyncio
async def test_ctrl_d_u_half_page(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test(size=(80, 12)) as pilot:
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        scroll = app.screen.query_one("#help-scroll")
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert scroll.scroll_offset.y > 0
        down = scroll.scroll_offset.y
        await pilot.press("ctrl+u")
        await pilot.pause()
        assert scroll.scroll_offset.y < down


@pytest.mark.asyncio
async def test_help_topic_shows_command_help(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _type_command(pilot, "help sort")
        assert isinstance(app.screen, HelpScreen)
        body = app.screen.query_one("#help-body")
        text = body.render()
        assert "sort" in text.plain.lower()
        assert "field" in text.plain.lower()


@pytest.mark.asyncio
async def test_help_unknown_topic_stays_in_editor(sample_deck_path: Path) -> None:
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _type_command(pilot, "help nonexistent")
        assert not isinstance(app.screen, HelpScreen)
        from vimtg.tui.widgets.command_line import CommandLine
        cl = app.screen.query_one(CommandLine)
        assert "No help for: nonexistent" in cl.message

"""End-to-end visual integration tests using Textual's pilot API.

These tests exercise the full mounted-widget render path — not just unit-level
`.render()` calls — to catch issues that only surface when widgets compose
inside a real Textual screen (CSS layout, reactive watchers, focus state).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.editor.modes import Mode
from vimtg.tui.app import VimTGApp


@pytest.mark.asyncio
async def test_editor_renders_status_line_in_normal_mode(sample_deck_path: Path) -> None:
    """When a deck is loaded, the status line must show NORMAL mode + filename."""
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        from vimtg.tui.widgets.status_line import StatusLine
        status_lines = list(app.screen.query(StatusLine))
        assert status_lines, "StatusLine widget must be mounted"
        status = status_lines[0]
        text = status.render()
        assert "-- NORMAL --" in text.plain
        assert sample_deck_path.name in text.plain


@pytest.mark.asyncio
async def test_editor_renders_deck_buffer_content(sample_deck_path: Path) -> None:
    """The deck view must render at least one card name from the loaded file."""
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        from vimtg.tui.widgets.deck_view import DeckView
        deck_views = list(app.screen.query(DeckView))
        assert deck_views, "DeckView widget must be mounted"
        text = deck_views[0].render()
        # sample_burn.deck contains "Lightning Bolt"
        assert "Lightning Bolt" in text.plain


@pytest.mark.asyncio
async def test_command_line_shows_colon_prefix_after_keypress(
    sample_deck_path: Path,
) -> None:
    """Pressing `:` in normal mode must activate the command line prefix."""
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("colon")
        await pilot.pause()
        from vimtg.tui.widgets.command_line import CommandLine
        cls = list(app.screen.query(CommandLine))
        assert cls
        assert cls[0].prefix == ":"


@pytest.mark.asyncio
async def test_status_line_reflects_mode_change_to_insert(
    sample_deck_path: Path,
) -> None:
    """Entering INSERT mode must update the status line badge."""
    app = VimTGApp(deck_path=sample_deck_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("o")  # open new line / enter insert-like mode
        await pilot.pause()
        from vimtg.tui.widgets.status_line import StatusLine
        statuses = list(app.screen.query(StatusLine))
        assert statuses
        # We expect a mode change — at least, no longer NORMAL or a different label
        text = statuses[0].render()
        assert statuses[0].mode != Mode.NORMAL or "INSERT" in text.plain

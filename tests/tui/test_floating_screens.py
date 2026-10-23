"""Every auxiliary view is the same floating window: a modal box over
the editor (which stays on the stack, dimmed behind it), titled on its
top border, its close keys on the bottom border. A view opened from
another one floats above both."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App
from textual.screen import Screen

from tests.tui.test_merge_screen import _make_screen, _Recorder
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.floating import FloatingScreen
from vimtg.tui.screens.help_screen import HelpScreen
from vimtg.tui.screens.history_screen import HistoryScreen
from vimtg.tui.screens.main_screen import MainScreen

_DECK = "// Deck: Burn\n// Format: modern\n\n4 Goblin Guide\n20 Mountain\n36 Lava Spike\n"


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(_DECK, encoding="utf-8")
    return path


def _assert_floating(app: App[None], title: str) -> FloatingScreen[None]:
    screen = app.screen
    assert isinstance(screen, FloatingScreen), type(screen).__name__
    assert title in str(screen.window.border_title)
    assert "q" in str(screen.window.border_subtitle)
    # The editor is still underneath, not replaced
    assert any(isinstance(s, MainScreen) for s in app.screen_stack[:-1])
    return screen


async def _ex(app: VimTGApp, pilot, text: str) -> None:  # type: ignore[no-untyped-def]
    main = next(s for s in app.screen_stack if isinstance(s, MainScreen))
    main._execute_ex(text)
    await pilot.pause()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "title"),
    [
        ("help", "Help"),
        ("help sort", "sort"),
        ("messages", "Messages"),
        ("config", "Settings"),
        ("hand seed=1", "Sample hand"),
    ],
)
async def test_ex_command_views_float_over_the_editor(
    tmp_path: Path, command: str, title: str
) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await _ex(app, pilot, command)
        screen = _assert_floating(app, title)
        await pilot.press("q")
        await pilot.pause()
        assert app.screen is not screen
        assert isinstance(app.screen, MainScreen)


@pytest.mark.asyncio
async def test_help_from_history_floats_above_history(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await _ex(app, pilot, "history")
        history = _assert_floating(app, "History")
        await pilot.press("question_mark")
        await pilot.pause()
        help_screen = _assert_floating(app, "history")
        assert isinstance(help_screen, HelpScreen)
        assert app.screen_stack[-2] is history
        await pilot.press("q")
        await pilot.pause()
        assert isinstance(app.screen, HistoryScreen)


class _Host(App[None]):
    def __init__(self, screen: Screen[None]) -> None:
        super().__init__()
        self._target = screen

    def on_mount(self) -> None:
        self.push_screen(self._target)


@pytest.mark.asyncio
async def test_merge_screen_is_a_titled_floating_window() -> None:
    screen = _make_screen(_Recorder())
    app = _Host(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, FloatingScreen)
        assert "Merge" in str(screen.window.border_title)
        assert "abort" in str(screen.window.border_subtitle)

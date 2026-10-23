"""Every way into the tutor: `vimtg tutor`, `:Tutor`, and the greeter's `t`.

Inside the app, `:Tutor` and `t` exit with LAUNCH_TUTOR; the CLI then
opens the lesson deck in its sandbox (and does so again if the tutor
itself runs `:Tutor`).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from tests.tui.test_greeter_command_line import _command, _host
from vimtg.cli import main
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.help_screen import HelpScreen
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tutor import LAUNCH_TUTOR, lesson_text


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text("// Deck: Burn\n\n4 Lightning Bolt\n", encoding="utf-8")
    return path


async def _type(pilot, text: str) -> None:  # type: ignore[no-untyped-def]
    await pilot.press("colon")
    for ch in text:
        await pilot.press({" ": "space", "!": "exclamation_mark"}.get(ch, ch))
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["Tutor", "tutor"])
async def test_tutor_command_leaves_for_the_tutor(tmp_path: Path, command: str) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _type(pilot, command)
    assert app.return_value == LAUNCH_TUTOR


@pytest.mark.asyncio
async def test_tutor_refuses_unsaved_changes_without_bang(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        main_screen = app.screen
        assert isinstance(main_screen, MainScreen)
        await pilot.press("G", "plus")
        assert main_screen._state.modified
        await _type(pilot, "Tutor")
        cl = main_screen.query_one("#command-line", CommandLine)
        assert cl.message.startswith("E37")
        assert app.return_value is None
        await _type(pilot, "Tutor!")
    assert app.return_value == LAUNCH_TUTOR


@pytest.mark.asyncio
@pytest.mark.parametrize("keys", [("t",), ("colon", "T", "u", "t", "o", "r", "enter")])
async def test_greeter_opens_the_tutor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, keys: tuple[str, ...],
) -> None:
    app, _screen = _host(tmp_path, monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        for key in keys:
            await pilot.press(key)
        await pilot.pause()
    assert app.return_value == LAUNCH_TUTOR


@pytest.mark.asyncio
async def test_greeter_menu_lists_the_tutorial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vimtg.tui.screens.greeter import GreeterView

    app, screen = _host(tmp_path, monkeypatch)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        assert "Tutorial" in screen.query_one(GreeterView).render().plain
        await _command(pilot, "help tutor")
        assert isinstance(app.screen, HelpScreen)


def test_cli_follows_the_app_into_the_tutor(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deck the user had open exits with LAUNCH_TUTOR; the CLI then
    runs the editor again on a fresh lesson deck."""
    opened: list[str | None] = []
    results = iter([LAUNCH_TUTOR, None])

    def fake_app(deck_path: Path | None = None) -> MagicMock:
        opened.append(deck_path.read_text(encoding="utf-8") if deck_path else None)
        app = MagicMock()
        app.run.return_value = next(results)
        return app

    import vimtg.tui.app as app_mod

    monkeypatch.setattr(app_mod, "VimTGApp", MagicMock(side_effect=fake_app))
    result = CliRunner().invoke(main, [])
    assert result.exit_code == 0, result.output
    assert opened == [None, lesson_text()]

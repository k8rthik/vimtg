"""Listing commands (:registers, :marks, :categories, :plans,
:validate, :g//p) show their output on the command line
when it fits on one line, and in the floating pager, one entry per line,
when it does not: vim's more-prompt, instead of output cut off at the
terminal edge."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.help_screen import HelpScreen
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine

_CARDS = [
    "Goblin Guide", "Monastery Swiftspear", "Eidolon of the Great Revel",
    "Lightning Bolt", "Lava Spike", "Rift Bolt", "Skewer the Critics",
]


def _deck(tmp_path: Path) -> Path:
    lines = ["// Deck: Burn", "// Format: modern", ""]
    for i, name in enumerate(_CARDS):
        lines.append(f"4 {name}  @cat{i}")
    path = tmp_path / "burn.deck"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _main(app: VimTGApp) -> MainScreen:
    return next(s for s in app.screen_stack if isinstance(s, MainScreen))


async def _ex(app: VimTGApp, pilot, text: str) -> None:  # type: ignore[no-untyped-def]
    _main(app)._execute_ex(text)
    await pilot.pause()


def _pager_body(app: VimTGApp) -> str:
    assert isinstance(app.screen, HelpScreen), type(app.screen).__name__
    return str(app.screen.query_one("#help-body").render())


@pytest.mark.asyncio
async def test_registers_that_overflow_open_the_pager(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(60, 30)) as pilot:
        await pilot.pause()
        for row, register in zip(range(5, 11), "abcdef", strict=True):
            await _ex(app, pilot, f"{row}g/./y {register}")
        await _ex(app, pilot, "registers")
        body = _pager_body(app)
        assert "Registers" in str(app.screen.window.border_title)
        for register in "abcdef":
            assert f'"{register} ' in body
        assert len(body.strip().splitlines()) >= 6
        await pilot.press("q")
        await pilot.pause()
        assert app.screen is _main(app)


@pytest.mark.asyncio
async def test_output_that_fits_stays_on_the_command_line(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await _ex(app, pilot, "5g/./y a")
        await _ex(app, pilot, "registers a")
        assert app.screen is _main(app)
        cl = _main(app).query_one("#command-line", CommandLine)
        assert cl.message.startswith('"a 4 Goblin Guide')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "title", "expected"),
    [
        ("categories", "Categories", "@cat3"),
        ("g/o/p", "Matches", "Monastery Swiftspear"),
    ],
)
async def test_long_listings_open_the_pager(
    tmp_path: Path, command: str, title: str, expected: str
) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(60, 30)) as pilot:
        await pilot.pause()
        await _ex(app, pilot, command)
        body = _pager_body(app)
        assert title in str(app.screen.window.border_title)
        assert expected in body
        assert len(body.strip().splitlines()) > 1


@pytest.mark.asyncio
async def test_validate_problems_open_the_pager_one_per_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.deck"
    path.write_text(
        "// Deck: Bad\n// Format: modern\n\n"
        + "".join(f"9 Card Number {i}\n" for i in range(6)),
        encoding="utf-8",
    )
    app = VimTGApp(deck_path=path)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        await _ex(app, pilot, "validate")
        body = _pager_body(app)
        lines = body.strip().splitlines()
        assert "errors" in lines[0]
        assert sum("Card Number" in line for line in lines) >= 6


@pytest.mark.asyncio
async def test_pager_output_is_kept_for_messages(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(60, 30)) as pilot:
        await pilot.pause()
        await _ex(app, pilot, "categories")
        await pilot.press("q")
        await pilot.pause()
        await _ex(app, pilot, "messages")
        assert "@cat6" in _pager_body(app)

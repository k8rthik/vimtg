"""Combos overlay (Textual pilot): :combos / :combo / Space c look the
deck up on Commander Spellbook, list its combos and those one card
away, and Enter on a one-away row adds the missing card."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.combo_screen import ComboScreen
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine

FIXTURE = Path(__file__).parent.parent / "fixtures" / "spellbook" / "find_my_combos_thassa.json"
POST = "vimtg.services.spellbook.httpx.post"

_DECK = (
    "// Deck: Oracle\n"
    "// Format: vintage\n"
    "\n"
    "1 Thassa's Oracle\n"
    "1 Demonic Consultation\n"
    "1 Sol Ring\n"
    "\n"
    "SB: 1 Duress\n"
)


@pytest.fixture(autouse=True)
def _live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIMTG_NO_SPELLBOOK", raising=False)
    monkeypatch.delenv("VIMTG_SPELLBOOK_FIXTURE", raising=False)


def _ok(*_args: object, **_kwargs: object) -> httpx.Response:
    return httpx.Response(
        200,
        json=json.loads(FIXTURE.read_text(encoding="utf-8")),
        request=httpx.Request("POST", "https://backend.commanderspellbook.com/find-my-combos"),
    )


def _deck(tmp_path: Path, text: str = _DECK) -> Path:
    path = tmp_path / "oracle.deck"
    path.write_text(text, encoding="utf-8")
    return path


async def _command(pilot: Any, text: str) -> None:
    await pilot.press("colon")
    for ch in text:
        await pilot.press("space" if ch == " " else ch)
    await pilot.press("enter")
    await pilot.pause()


async def _settle(pilot: Any, app: VimTGApp) -> None:
    await app.workers.wait_for_complete()
    await pilot.pause()


def _combos(app: VimTGApp) -> ComboScreen:
    screen = app.screen
    assert isinstance(screen, ComboScreen)
    return screen


def _body(app: VimTGApp) -> str:
    return str(app.screen.query_one("#combo-body").render())


def _footer(app: VimTGApp) -> str:
    return str(app.screen.query_one("#combo-footer").render())


def _main(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


@pytest.mark.asyncio
async def test_combos_command_lists_both_sections(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(POST, side_effect=_ok) as post:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _command(pilot, "combos")
            await _settle(pilot, app)
            screen = _combos(app)
            assert screen.window.border_title == " Combos — oracle.deck "
            assert "Commander Spellbook" in str(screen.window.border_subtitle)
            body = _body(app)
            assert "In this deck (1)" in body
            assert "742-1295" in body
            assert "Demonic Consultation + Thassa's Oracle" in body
            assert "Exile your library, Win the game" in body
            assert "One card away (3)" in body
            assert body.index("Hullbreaker Horror") < body.index("Tainted Pact")
            assert "1295-4400" not in body
    sent = post.call_args.kwargs["json"]
    assert sorted(e["card"] for e in sent["main"]) == [
        "Demonic Consultation", "Sol Ring", "Thassa's Oracle",
    ]
    assert sent["commanders"] == []


@pytest.mark.asyncio
async def test_leader_c_and_alias_open_the_overlay(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(POST, side_effect=_ok):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("space", "c")
            await _settle(pilot, app)
            assert "In this deck (1)" in _body(app)
            await pilot.press("q")
            await pilot.pause()
            _main(app)
            await _command(pilot, "combo")
            await _settle(pilot, app)
            assert "One card away (3)" in _body(app)
            await pilot.press("escape")
            await pilot.pause()
            _main(app)


@pytest.mark.asyncio
async def test_status_while_looking_up(tmp_path: Path) -> None:
    release = threading.Event()

    def slow(*args: object, **kwargs: object) -> httpx.Response:
        release.wait(5)
        return _ok()

    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(POST, side_effect=slow):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _command(pilot, "combos")
            assert "Looking up combos…" in _body(app)
            release.set()
            await _settle(pilot, app)
            assert "In this deck (1)" in _body(app)


@pytest.mark.asyncio
async def test_enter_on_a_one_away_row_adds_the_missing_card(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(POST, side_effect=_ok):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _command(pilot, "combos")
            await _settle(pilot, app)
            assert "already in the deck" in _footer(app)
            await pilot.press("j", "j")
            await pilot.pause()
            assert "Enter adds Tainted Pact" in _footer(app)
            assert "commanderspellbook.com/combo/1295-3093/" in _footer(app)
            await pilot.press("enter")
            await pilot.pause()
            main = _main(app)
            text = main._state.buffer.to_text()
            assert "1 Tainted Pact" in text.split("SB:")[0]
            assert main._state.modified
            message = str(main.query_one("#command-line", CommandLine).render())
            assert "Added Tainted Pact" in message
            await pilot.press("u")
            await pilot.pause()
            assert "Tainted Pact" not in main._state.buffer.to_text()


@pytest.mark.asyncio
async def test_enter_on_an_included_row_adds_nothing(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(POST, side_effect=_ok):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _command(pilot, "combos")
            await _settle(pilot, app)
            before = app.screen_stack[0]
            await pilot.press("enter")
            await pilot.pause()
            _combos(app)
            assert before is app.screen_stack[0]


@pytest.mark.asyncio
async def test_navigation_wraps_to_last_and_first(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(POST, side_effect=_ok):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _command(pilot, "combos")
            await _settle(pilot, app)
            await pilot.press("G")
            await pilot.pause()
            assert "Enter adds Tidespout Tyrant" in _footer(app)
            await pilot.press("g", "g")
            await pilot.pause()
            assert "742-1295" in _footer(app)
            await pilot.press("k")
            await pilot.pause()
            assert "742-1295" in _footer(app)


@pytest.mark.asyncio
async def test_lookup_failure_shows_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIMTG_NO_SPELLBOOK", "1")
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(POST, side_effect=AssertionError("network hit")):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _command(pilot, "combos")
            await _settle(pilot, app)
            assert "Combo lookups disabled (VIMTG_NO_SPELLBOOK)" in _body(app)
            await pilot.press("enter")
            await pilot.pause()
            _combos(app)


@pytest.mark.asyncio
async def test_note_is_shown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIMTG_SPELLBOOK_FIXTURE", str(FIXTURE))
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await _command(pilot, "combos")
        await _settle(pilot, app)
        assert "VIMTG_SPELLBOOK_FIXTURE" in _body(app)


@pytest.mark.asyncio
async def test_empty_deck_says_why_without_a_lookup(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path, "// Deck: Empty\n\nSB: 1 Duress\n"))
    with patch(POST, side_effect=AssertionError("network hit")):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _command(pilot, "combos")
            main = _main(app)
            message = str(main.query_one("#command-line", CommandLine).render())
            assert "No cards in the deck" in message


@pytest.mark.asyncio
async def test_closing_before_the_reply_is_safe(tmp_path: Path) -> None:
    release = threading.Event()

    def slow(*args: object, **kwargs: object) -> httpx.Response:
        release.wait(5)
        return _ok()

    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(POST, side_effect=slow):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _command(pilot, "combos")
            await pilot.press("q")
            await pilot.pause()
            release.set()
            await _settle(pilot, app)
            _main(app)


@pytest.mark.asyncio
async def test_selection_stays_in_view_in_a_short_terminal(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    with patch(POST, side_effect=_ok):
        async with app.run_test(size=(120, 16)) as pilot:
            await pilot.pause()
            await _command(pilot, "combos")
            await _settle(pilot, app)
            scroll = app.screen.query_one("#combo-scroll")
            assert scroll.scroll_y == 0
            await pilot.press("G")
            await pilot.pause()
            lines = _body(app).splitlines()
            last = next(i for i, line in enumerate(lines) if "542-5034" in line)
            top = int(scroll.scroll_y)
            assert top > 0
            assert top <= last and last + 1 < top + scroll.size.height

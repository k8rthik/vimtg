"""Docs-vs-behaviour fixes found by the 1.0 fresh-user audit: :search,
"No matches", pop-up notices in :messages, and config warnings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.config.paths import config_dir, db_path
from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card
from vimtg.editor.modes import Mode
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.help_screen import HelpScreen
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.search_results import SearchResults

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "scryfall_real_shape.json"


@pytest.fixture
def seeded_db(db_factory):  # type: ignore[no-untyped-def]
    db_file = db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    repo = CardRepository(db_factory(db_file))
    repo.replace_all(
        [Card.from_scryfall(d) for d in json.loads(_FIXTURES.read_text(encoding="utf-8"))]
    )
    return repo


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "deck.deck"
    path.write_text("4 Lightning Bolt\n", encoding="utf-8")
    return path


def _main(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


async def _ex(pilot, app: VimTGApp, command: str) -> None:  # type: ignore[no-untyped-def]
    await pilot.press(":")
    for ch in command:
        await pilot.press("space" if ch == " " else ch)
    await pilot.press("enter")
    await app.workers.wait_for_complete()
    await pilot.pause()


async def _messages_body(pilot, app: VimTGApp) -> str:  # type: ignore[no-untyped-def]
    await _ex(pilot, app, "messages")
    assert isinstance(app.screen, HelpScreen)
    return str(app.screen.query_one("#help-body").render())


# ── :search ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_command_opens_overlay_with_query(seeded_db, tmp_path: Path) -> None:
    """Documented in README, docs/commands.md and docs/search.md, but
    used to fail with 'Unknown command: search'."""
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await _ex(pilot, app, "search t:creature -c:w")
        screen = _main(app)
        assert screen._state.mode_mgr.current == Mode.INSERT
        cl = screen.query_one("#command-line", CommandLine)
        assert cl.text == "t:creature -c:w"
        sr = screen.query_one("#search-results", SearchResults)
        assert sr.display is True
        assert "Thrasios, Triton Hero" in {c.name for c in sr.results}

        # Enter adds the selected card, as with o
        chosen = sr.get_selected()
        assert chosen is not None
        await pilot.press("enter")
        await pilot.pause()
        assert chosen.name in screen._state.buffer.to_text()
        assert screen._state.mode_mgr.current == Mode.NORMAL


@pytest.mark.asyncio
async def test_search_ignores_a_remapped_o(seeded_db, tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await _ex(pilot, app, "map o dd")
        await _ex(pilot, app, "search bolt")
        screen = _main(app)
        assert screen._state.mode_mgr.current == Mode.INSERT
        assert "Lightning Bolt" in screen._state.buffer.to_text()


@pytest.mark.asyncio
async def test_no_matches_says_so(seeded_db, tmp_path: Path) -> None:
    """A query matching nothing used to hide the overlay silently."""
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await _ex(pilot, app, "search zzzznotacard")
        sr = _main(app).query_one("#search-results", SearchResults)
        assert sr.display is True
        assert sr.results == []
        assert "No matches" in str(sr.render())

        # Results replace the notice again
        for _ in "zzzznotacard":
            await pilot.press("backspace")
        for ch in "bolt":
            await pilot.press(ch)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert sr.results
        assert "No matches" not in str(sr.render())


# ── :messages records pop-up notices ─────────────────────────────


@pytest.mark.asyncio
async def test_notices_are_kept_for_messages(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.notify("Recovered; backup at /tmp/cards.db.corrupt-1", title="Card database")
        app._fail_auto_sync("offline")
        app.notify("[b]literal[/b]", markup=False)
        await pilot.pause()
        body = await _messages_body(pilot, app)
        assert "Card database: Recovered; backup at /tmp/cards.db.corrupt-1" in body
        # Shown on the command line and as a pop-up, recorded once
        assert body.count("Card sync failed: offline") == 1
        assert "[b]literal[/b]" in body


@pytest.mark.asyncio
async def test_messages_survive_editing_another_deck(tmp_path: Path) -> None:
    other = tmp_path / "other.deck"
    other.write_text("4 Shock\n", encoding="utf-8")
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        _main(app).show_message("before the switch")
        await pilot.press("escape")
        await _ex(pilot, app, f"e {other}")
        assert "before the switch" in await _messages_body(pilot, app)


@pytest.mark.asyncio
async def test_bad_keybindings_warn_instead_of_crashing(tmp_path: Path) -> None:
    """A wrong-shape [keybindings] table crashed startup with a traceback."""
    cfg = config_dir()
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.toml").write_text(
        '[editor]\nshow_prices = "no"\n[keybindings]\nnormal = "x"\n', encoding="utf-8",
    )
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)
        body = await _messages_body(pilot, app)
        assert "[keybindings.normal] must be a table" in body
        assert "show_prices must be true or false" in body

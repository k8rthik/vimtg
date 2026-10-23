"""Regressions from the TUI state audit: a selection that outlived its
mode, stale and late card-search results, the / prompt completing ex
commands, which-key after a paste, and history restores."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from textual.app import App

from vimtg.data.card_repository import CardRepository
from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import CommandRegistry
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import ParsedAction
from vimtg.editor.session import handle_mode_switch
from vimtg.services.search_service import SearchService
from vimtg.tui.app import VimTGApp
from vimtg.tui.screens.main_screen import MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.search_results import SearchResults
from vimtg.tui.widgets.which_key import WhichKey

CANONICAL = (
    "// Deck: Burn\n// Format: modern\n// Tags:\n\n"
    "// Creature\n4 Goblin Guide\n4 Monastery Swiftspear\n\n"
    "// Instant\n4 Lightning Bolt\n4 Searing Blaze\n4 Skullcrack\n\n"
    "// Land\n20 Mountain\n"
)


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(CANONICAL, encoding="utf-8")
    return path


def _reraise(exc: Exception) -> None:
    raise exc


def _feed(scr: MainScreen, keys: list[str]) -> None:
    scr.recover_from_crash = _reraise  # type: ignore[method-assign]
    for key in keys:
        scr._process_key(key)


def _screen(app: VimTGApp) -> MainScreen:
    scr = app.screen
    assert isinstance(scr, MainScreen)
    return scr


def _cards(scr: MainScreen) -> list[str]:
    buf = scr._state.buffer
    return [buf.get_line(i).text for i in range(buf.line_count()) if buf.is_card_line(i)]


class _Host(App[None]):
    def __init__(self, screen: MainScreen) -> None:
        super().__init__()
        self._target = screen

    def on_mount(self) -> None:
        self.push_screen(self._target)


@pytest.fixture
def wired_repo(db_factory):  # type: ignore[no-untyped-def]
    fixtures = Path(__file__).parent.parent / "fixtures" / "scryfall_sample.json"
    repo = CardRepository(db_factory())
    repo.bulk_insert([Card.from_scryfall(d) for d in json.loads(fixtures.read_text())])
    return repo


def _wired_screen(repo: CardRepository) -> MainScreen:
    return MainScreen(
        buffer=Buffer.from_text("// Creatures\n4 Goblin Guide\n"),
        registry=CommandRegistry(),
        search_service=SearchService(card_repo=repo),
        card_repo=repo,
    )


def _open_below(scr: MainScreen, row: int) -> None:
    scr._state.cursor = Cursor(row=row)
    handle_mode_switch(scr._state, ParsedAction("mode_switch", "o"))


class TestASelectionDoesNotOutliveItsMode:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "keys",
        [
            ["6", "G", "V", "i", "enter", "4", "j", "d", "d"],
            ["6", "G", "V", "/", "b", "o", "l", "t", "enter", "4", "j", "d", "d"],
            ["6", "G", "V", ":", "1", "enter", "4", "j", "d", "d"],
        ],
        ids=["line-edit", "search", "ex-command"],
    )
    async def test_dd_after_leaving_visual_deletes_one_line(
        self, tmp_path: Path, keys: list[str]
    ) -> None:
        # The anchor used to survive i / / / : so the next dd deleted
        # every line between it and the cursor
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            before = len(_cards(scr))
            _feed(scr, keys)
            assert scr._state.visual_anchor is None
            assert len(_cards(scr)) == before - 1


class TestCardSearchResults:
    @pytest.mark.asyncio
    async def test_a_cancelled_search_never_inserts_its_result(self, wired_repo) -> None:  # type: ignore[no-untyped-def]
        scr = _wired_screen(wired_repo)
        app = _Host(scr)
        async with app.run_test() as pilot:
            await pilot.pause()
            bolt = wired_repo.get_by_name("Lightning Bolt")
            _open_below(scr, 1)
            scr._update_search_results([bolt])
            scr._apply_exit_to_normal()  # Escape
            _open_below(scr, 1)
            scr._apply_enter_card_search()
            scr._confirm_insert()  # Enter with nothing typed
            assert scr._find_card_line("Lightning Bolt") is None

    @pytest.mark.asyncio
    async def test_a_new_search_opens_hidden_and_empty(self, wired_repo) -> None:  # type: ignore[no-untyped-def]
        scr = _wired_screen(wired_repo)
        app = _Host(scr)
        async with app.run_test() as pilot:
            await pilot.pause()
            bolt = wired_repo.get_by_name("Lightning Bolt")
            _open_below(scr, 1)
            scr._update_search_results([bolt])
            scr._apply_exit_to_normal()  # Escape
            _open_below(scr, 1)
            scr._apply_enter_card_search()
            sr = scr.query_one("#search-results", SearchResults)
            assert sr.display is False  # no "No matches" box before a query
            assert sr.results == []

    @pytest.mark.asyncio
    async def test_a_late_result_does_not_reopen_the_overlay(self, wired_repo) -> None:  # type: ignore[no-untyped-def]
        scr = _wired_screen(wired_repo)
        app = _Host(scr)
        async with app.run_test() as pilot:
            await pilot.pause()
            bolt = wired_repo.get_by_name("Lightning Bolt")
            _open_below(scr, 1)
            scr._apply_enter_card_search()
            generation = scr._search_generation
            scr._confirm_insert()  # Enter before the worker returned
            scr._apply_search_results("lav", [bolt], generation)
            sr = scr.query_one("#search-results", SearchResults)
            assert sr.display is False
            assert sr.results == []
            # A worker from the live generation still shows its results
            _open_below(scr, 1)
            scr._apply_enter_card_search()
            scr._apply_search_results("lav", [bolt], scr._search_generation)
            assert sr.display is True and sr.results == [bolt]


class TestSearchPromptKeys:
    @pytest.mark.asyncio
    async def test_tab_does_not_turn_the_pattern_into_an_ex_command(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, ["/", "s", "o", "tab", "enter"])
            message = scr.query_one("#command-line", CommandLine).message
            assert "sort" not in message
            assert message.endswith("so")


class TestPasteCancelsAPendingOperator:
    @pytest.mark.asyncio
    async def test_which_key_hides_with_the_operator_it_described(self, tmp_path: Path) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            _feed(scr, ["d"])
            wk = scr.query_one("#which-key", WhichKey)
            assert wk.pending_key == "d"
            scr._handle_paste("4 Shock\n")
            await pilot.pause()
            assert wk.display is False and wk.pending_key == ""
            assert any("Shock" in line for line in _cards(scr))


class TestHistoryRestoreOfTheSavedText:
    @pytest.mark.asyncio
    async def test_an_identical_snapshot_does_not_mark_the_deck_modified(
        self, tmp_path: Path
    ) -> None:
        app = VimTGApp(deck_path=_deck(tmp_path))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            scr = _screen(app)
            scr._on_vcs_state(scr._state.buffer.to_text(), "restore")
            assert scr._state.modified is False
            scr._on_vcs_state("// Deck: Burn\n\n4 Opt\n", "restore")
            assert scr._state.modified is True

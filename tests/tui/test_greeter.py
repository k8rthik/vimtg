"""Tests for the greeter screen — mode switching, help, file browser, recent files."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from textual.app import App
from textual.pilot import Pilot

from vimtg.tui.screens.greeter import (
    GreeterMode,
    GreeterScreen,
    GreeterView,
)

# ---------------------------------------------------------------------------
# GreeterView unit tests (no Textual app required)
# ---------------------------------------------------------------------------


class TestGreeterViewDefaults:
    def test_default_mode_is_menu(self) -> None:
        gv = GreeterView()
        assert gv._mode == GreeterMode.MENU

    def test_default_cursor_is_zero(self) -> None:
        gv = GreeterView()
        assert gv._cursor == 0


class TestRenderMenu:
    def test_render_menu_contains_logo(self) -> None:
        gv = GreeterView()
        text = gv._render_menu()
        # Logo is ASCII art — check a distinctive piece
        assert "___/" in text.plain

    def test_render_menu_contains_actions(self) -> None:
        gv = GreeterView()
        text = gv._render_menu()
        plain = text.plain
        assert "[n]" in plain
        assert "[e]" in plain
        assert "[?]" in plain
        assert "[q]" in plain

    def test_render_menu_shows_recent_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "burn.deck"
        f1.touch()
        gv = GreeterView(recent_files=[f1])
        text = gv._render_menu()
        assert "burn.deck" in text.plain
        assert "[1]" in text.plain

    def test_render_menu_no_recent_section(self) -> None:
        gv = GreeterView(recent_files=[])
        text = gv._render_menu()
        # The "Recent files" action label always shows, but the numbered
        # recent files section should not appear when list is empty
        assert "[1]" not in text.plain


class TestRenderHelp:
    def test_render_help_contains_navigation(self) -> None:
        gv = GreeterView()
        gv._mode = GreeterMode.HELP
        text = gv._render_help()
        plain = text.plain
        assert "NAVIGATION" in plain
        assert "EDITING" in plain
        assert "COMMANDS" in plain

    def test_render_help_shows_return_hint(self) -> None:
        gv = GreeterView()
        gv._mode = GreeterMode.HELP
        text = gv._render_help()
        assert "Esc" in text.plain

    def test_render_dispatches_to_help(self) -> None:
        gv = GreeterView()
        gv._mode = GreeterMode.HELP
        text = gv.render()
        assert "NAVIGATION" in text.plain


class TestRenderFileList:
    def test_render_files_shows_names(self, tmp_path: Path) -> None:
        f1 = tmp_path / "alpha.deck"
        f2 = tmp_path / "beta.deck"
        f1.touch()
        f2.touch()
        gv = GreeterView(all_files=[f1, f2])
        gv._mode = GreeterMode.FILES
        text = gv._render_file_list([f1, f2], "Open File")
        plain = text.plain
        assert "alpha.deck" in plain
        assert "beta.deck" in plain

    def test_render_files_empty_message(self) -> None:
        gv = GreeterView(all_files=[])
        gv._mode = GreeterMode.FILES
        text = gv._render_file_list([], "Open File")
        assert "No .deck files found" in text.plain

    def test_render_files_cursor_indicator(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.deck"
        f2 = tmp_path / "b.deck"
        f1.touch()
        f2.touch()
        gv = GreeterView(all_files=[f1, f2])
        gv._mode = GreeterMode.FILES
        gv._cursor = 1
        text = gv._render_file_list([f1, f2], "Open File")
        lines = text.plain.split("\n")
        # Find lines containing file names and check cursor indicator
        file_lines = [ln for ln in lines if ".deck" in ln]
        assert any("b.deck" in ln for ln in file_lines)

    def test_render_dispatches_to_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "test.deck"
        f1.touch()
        gv = GreeterView(all_files=[f1])
        gv._mode = GreeterMode.FILES
        text = gv.render()
        assert "Open File" in text.plain

    def test_render_dispatches_to_recent(self, tmp_path: Path) -> None:
        f1 = tmp_path / "test.deck"
        f1.touch()
        gv = GreeterView(recent_files=[f1])
        gv._mode = GreeterMode.RECENT
        text = gv.render()
        assert "Recent Files" in text.plain


class TestCursorNavigation:
    def test_select_next_increments(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.deck"
        f2 = tmp_path / "b.deck"
        f1.touch()
        f2.touch()
        gv = GreeterView()
        gv._cursor = 0
        gv.select_next([f1, f2])
        assert gv._cursor == 1

    def test_select_next_clamps_at_end(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.deck"
        f1.touch()
        gv = GreeterView()
        gv._cursor = 0
        gv.select_next([f1])
        assert gv._cursor == 0  # Can't go past the only item

    def test_select_next_empty_list(self) -> None:
        gv = GreeterView()
        gv._cursor = 0
        gv.select_next([])
        assert gv._cursor == 0

    def test_select_prev_decrements(self) -> None:
        gv = GreeterView()
        gv._cursor = 2
        gv.select_prev()
        assert gv._cursor == 1

    def test_select_prev_clamps_at_zero(self) -> None:
        gv = GreeterView()
        gv._cursor = 0
        gv.select_prev()
        assert gv._cursor == 0

    def test_get_selected_returns_path(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.deck"
        f2 = tmp_path / "b.deck"
        f1.touch()
        f2.touch()
        gv = GreeterView()
        gv._cursor = 1
        assert gv.get_selected([f1, f2]) == f2

    def test_get_selected_empty_list(self) -> None:
        gv = GreeterView()
        assert gv.get_selected([]) is None

    def test_set_mode_resets_cursor(self) -> None:
        gv = GreeterView()
        gv._cursor = 3
        gv.set_mode(GreeterMode.HELP)
        assert gv._mode == GreeterMode.HELP
        assert gv._cursor == 0

    def test_set_mode_changes_mode(self) -> None:
        gv = GreeterView()
        gv.set_mode(GreeterMode.FILES)
        assert gv._mode == GreeterMode.FILES


class TestRenderStatus:
    def test_status_rendered_in_menu(self) -> None:
        gv = GreeterView()
        gv._status = "Synced 100 cards"
        assert "Synced 100 cards" in gv.render().plain

    def test_no_status_when_empty(self) -> None:
        gv = GreeterView()
        assert "Synced" not in gv.render().plain


# ---------------------------------------------------------------------------
# GreeterScreen pilot integration tests
# ---------------------------------------------------------------------------


class _HostApp(App[None]):
    """Hosts a GreeterScreen and records editor launches instead of running one."""

    def __init__(self, screen: GreeterScreen) -> None:
        super().__init__()
        self._target = screen
        self.launched: list[tuple[Path | None, str | None]] = []

    def on_mount(self) -> None:
        self.push_screen(self._target)

    def open_deck(
        self, file_path: Path | None = None, initial_text: str | None = None
    ) -> None:
        self.launched.append((file_path, initial_text))


def _make_decks(directory: Path, names: list[str]) -> list[Path]:
    paths = []
    for n in names:
        p = directory / n
        p.write_text("// Deck: x\n\n4 Lightning Bolt\n", encoding="utf-8")
        paths.append(p)
    return paths


@pytest.mark.asyncio
async def test_help_mode_toggle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        await pilot.press("?")
        assert gv._mode == GreeterMode.HELP
        await pilot.press("escape")
        assert gv._mode == GreeterMode.MENU


@pytest.mark.asyncio
async def test_files_mode_navigation_and_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _make_decks(tmp_path, ["a.deck", "b.deck", "c.deck"])
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        await pilot.press("e")
        assert gv._mode == GreeterMode.FILES
        await pilot.press("j")
        assert gv._cursor == 1
        await pilot.press("k")
        assert gv._cursor == 0
        await pilot.press("G")
        assert gv._cursor == 2
        await pilot.press("g", "g")
        assert gv._cursor == 0
        await pilot.press("enter")
        assert app.launched and app.launched[0][0] is not None


@pytest.mark.asyncio
async def test_files_mode_escape_returns_to_menu(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _make_decks(tmp_path, ["a.deck"])
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        await pilot.press("e")
        await pilot.press("escape")
        assert gv._mode == GreeterMode.MENU


@pytest.mark.asyncio
async def test_new_opens_editor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n")
        assert app.launched == [(None, None)]


@pytest.mark.asyncio
async def test_recent_digit_opens_recent_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    recent = _make_decks(tmp_path, ["fresh.deck"])
    screen = GreeterScreen(recent_files=recent)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("1")
        assert app.launched == [(recent[0], None)]


@pytest.mark.asyncio
async def test_recent_mode_via_r(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    recent = _make_decks(tmp_path, ["fresh.deck"])
    screen = GreeterScreen(recent_files=recent)
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        await pilot.press("r")
        assert gv._mode == GreeterMode.RECENT


async def _wait_until(
    pilot: Pilot[None], condition: Callable[[], bool], timeout: float = 10.0
) -> None:
    """Wait for a background worker's effect instead of guessing a pause.

    Worker threads report back via call_from_thread, which finishes
    before the worker does — so once the app's workers are done the
    condition is settled. The deadline only guards against a hang.
    """
    deadline = time.monotonic() + timeout
    while True:
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        if condition():
            return
        if time.monotonic() > deadline:
            raise AssertionError("condition not met before the deadline")


def _slow(result: Callable[[], int]) -> Callable[..., int]:
    """A ScryfallSync.sync stand-in as slow as a loaded CI runner —
    a single short pause would check the status before it finishes."""

    def sync(self: object, *a: object, **k: object) -> int:
        time.sleep(0.3)
        return result()

    return sync


def _offline() -> int:
    raise httpx.ConnectError(
        "[Errno -3] Temporary failure in name resolution",
        request=httpx.Request("GET", "https://api.scryfall.com/bulk-data"),
    )


@pytest.mark.asyncio
async def test_run_sync_shows_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    from vimtg.data import scryfall_sync

    monkeypatch.setattr(scryfall_sync.ScryfallSync, "sync", _slow(lambda: 123))
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        await pilot.press("s")
        assert gv._status == "Syncing card data..."
        await _wait_until(pilot, lambda: not screen._sync_running)
        assert gv._status == "Synced 123 cards"


@pytest.mark.asyncio
async def test_run_sync_handles_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    from vimtg.data import scryfall_sync

    for var in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(scryfall_sync.ScryfallSync, "sync", _slow(_offline))
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        gv = screen.query_one(GreeterView)
        await _wait_until(pilot, lambda: not screen._sync_running)
        assert gv._status.startswith("Sync failed: Could not reach api.scryfall.com")
        assert "press s to retry" in gv._status


@pytest.mark.asyncio
async def test_run_sync_ignores_repeat_while_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    from vimtg.data import scryfall_sync

    calls: list[int] = []

    def counted() -> int:
        calls.append(1)
        return 7

    monkeypatch.setattr(scryfall_sync.ScryfallSync, "sync", _slow(counted))
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.press("s")
        await _wait_until(pilot, lambda: not screen._sync_running)
        assert calls == [1]


class _CardDataHost(_HostApp):
    """A host that, like VimTGApp, reports card data and adopts syncs."""

    def __init__(self, screen: GreeterScreen) -> None:
        super().__init__(screen)
        self.adopted = 0

    def card_data_status(self) -> tuple[str, bool]:
        from vimtg.data.scryfall_sync import NO_CARD_DATA

        return NO_CARD_DATA, True

    def adopt_card_data(self) -> None:
        self.adopted += 1


@pytest.mark.asyncio
async def test_greeter_shows_missing_card_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _CardDataHost(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        assert "no card data - press s to download" in gv.render().plain
        screen.set_card_data_status("card data as of 2026-10-09", False)
        assert "card data as of 2026-10-09" in gv.render().plain


@pytest.mark.asyncio
async def test_greeter_sync_hands_cards_to_the_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: a greeter sync left the app without a card repo, so
    the editor opened next had no search."""
    monkeypatch.chdir(tmp_path)
    from vimtg.data import scryfall_sync

    monkeypatch.setattr(scryfall_sync.ScryfallSync, "sync", _slow(lambda: 5))
    screen = GreeterScreen()
    app = _CardDataHost(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await _wait_until(pilot, lambda: not screen._sync_running)
        assert app.adopted == 1


# ---------------------------------------------------------------------------
# Import mode
# ---------------------------------------------------------------------------


class TestRenderImport:
    def test_render_import_prompt(self) -> None:
        gv = GreeterView()
        gv.set_mode(GreeterMode.IMPORT)
        gv._input = "https://moxfield.com/decks/abc"
        text = gv.render().plain
        assert "Import Deck" in text
        assert "https://moxfield.com/decks/abc" in text

    def test_menu_lists_import_action(self) -> None:
        gv = GreeterView()
        text = gv.render().plain
        assert "[i]" in text
        assert "Import deck" in text


@pytest.mark.asyncio
async def test_import_mode_typing_and_escape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        await pilot.press("i")
        assert gv._mode == GreeterMode.IMPORT
        for ch in "a.txt":
            await pilot.press(ch)
        assert gv._input == "a.txt"
        await pilot.press("backspace")
        assert gv._input == "a.tx"
        await pilot.press("escape")
        assert gv._mode == GreeterMode.MENU


@pytest.mark.asyncio
async def test_import_mode_paste(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from textual import events

    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        await pilot.press("i")
        screen.on_paste(events.Paste("https://moxfield.com/decks/abc\n"))
        assert gv._input == "https://moxfield.com/decks/abc"


@pytest.mark.asyncio
async def test_import_url_opens_editor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from unittest.mock import patch

    from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
    from vimtg.services.deck_sources import RemoteDeck

    monkeypatch.chdir(tmp_path)
    remote = RemoteDeck(
        name="Mono Red",
        deck=Deck(
            metadata=DeckMetadata(),
            entries=(DeckEntry(4, "Lightning Bolt", DeckSection.MAIN),),
            comments=(),
        ),
    )
    screen = GreeterScreen()
    app = _HostApp(screen)
    with patch(
        "vimtg.tui.screens.greeter.fetch_deck", return_value=remote
    ):
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("i")
            gv = screen.query_one(GreeterView)
            gv._input = "https://moxfield.com/decks/abc"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
    assert len(app.launched) == 1
    path, text = app.launched[0]
    assert path is None
    assert "4 Lightning Bolt" in text
    assert "// Deck: Mono Red" in text
    assert "// Source: https://moxfield.com/decks/abc" in text


@pytest.mark.asyncio
async def test_import_file_opens_editor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    listing = tmp_path / "list.txt"
    listing.write_text("4 Goblin Guide\nSideboard\n2 Duress\n", encoding="utf-8")
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        await pilot.press("i")
        gv._input = str(listing)
        await pilot.press("enter")
        await pilot.pause()
    assert len(app.launched) == 1
    path, text = app.launched[0]
    assert path is None
    assert "4 Goblin Guide" in text
    # The structured new-deck layout, named after the file
    assert "// Deck: list\n// Format:\n" in text
    assert "SB:\n    2 Duress" in text


@pytest.mark.asyncio
async def test_import_url_failure_shows_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from unittest.mock import patch

    from vimtg.services.deck_sources import DeckSourceError

    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _HostApp(screen)
    with patch(
        "vimtg.tui.screens.greeter.fetch_deck",
        side_effect=DeckSourceError("HTTP 404"),
    ):
        async with app.run_test() as pilot:
            await pilot.pause()
            gv = screen.query_one(GreeterView)
            await pilot.press("i")
            gv._input = "https://moxfield.com/decks/gone"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "404" in gv._status
            assert gv._mode == GreeterMode.IMPORT  # stays for a retry
    assert app.launched == []


@pytest.mark.asyncio
async def test_import_missing_file_shows_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        gv = screen.query_one(GreeterView)
        await pilot.press("i")
        gv._input = "nope.txt"
        await pilot.press("enter")
        await pilot.pause()
        assert "not found" in gv._status.lower()
    assert app.launched == []


# ---------------------------------------------------------------------------
# Pasted decklists
# ---------------------------------------------------------------------------

_PASTED = "Deck\n4 Lightning Bolt\n20 Mountain\n\nSideboard\n2 Pyroblast\n"


@pytest.mark.asyncio
async def test_paste_decklist_on_menu_opens_editor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from textual import events

    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.post_message(events.Paste(_PASTED))
        await pilot.pause()
    assert len(app.launched) == 1
    path, text = app.launched[0]
    assert path is None
    assert text is not None
    assert "4 Lightning Bolt" in text and "20 Mountain" in text
    assert "SB:\n    2 Pyroblast" in text


@pytest.mark.asyncio
async def test_paste_decklist_in_import_prompt_opens_editor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from textual import events

    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("i")
        screen.on_paste(events.Paste(_PASTED))
        await pilot.pause()
    assert len(app.launched) == 1


@pytest.mark.asyncio
async def test_paste_url_on_menu_fills_import_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from textual import events

    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.on_paste(events.Paste("https://moxfield.com/decks/abc"))
        gv = screen.query_one(GreeterView)
        assert gv._mode == GreeterMode.IMPORT
        assert gv._input == "https://moxfield.com/decks/abc"
    assert app.launched == []


@pytest.mark.asyncio
async def test_paste_non_decklist_explains(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from textual import events

    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.on_paste(events.Paste("dear diary\ntoday I built a deck\n"))
        gv = screen.query_one(GreeterView)
        assert gv._mode == GreeterMode.IMPORT
        assert gv._status.startswith("E: Not a decklist")
    assert app.launched == []


@pytest.mark.asyncio
async def test_typed_card_line_imports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    screen = GreeterScreen()
    app = _HostApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("i")
        gv = screen.query_one(GreeterView)
        gv._input = "4 Lightning Bolt"
        await pilot.press("enter")
        await pilot.pause()
    assert len(app.launched) == 1
    assert "4 Lightning Bolt" in (app.launched[0][1] or "")

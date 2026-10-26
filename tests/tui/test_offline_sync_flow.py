"""Offline / card-sync UX, clipboard and paste in the editor (Textual pilot).

No network: ScryfallSync.sync is replaced by fakes that load the
real-shape Scryfall fixture or raise the error a real offline run does.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from textual import events

from vimtg.config.paths import db_path
from vimtg.data import scryfall_sync
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.scryfall_sync import NO_CARD_DATA
from vimtg.domain.card import Card
from vimtg.services import clipboard
from vimtg.tui.app import VimTGApp, sync_progress_text
from vimtg.tui.screens.main_screen import OFFLINE_SEARCH_NOTICE, MainScreen
from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.search_results import SearchResults
from vimtg.tui.widgets.status_line import StatusLine


def _deck(tmp_path: Path, text: str = "4 Goblin Guide\n") -> Path:
    path = tmp_path / "t.deck"
    path.write_text(text, encoding="utf-8")
    return path


def _screen(app: VimTGApp) -> MainScreen:
    screen = app.screen
    assert isinstance(screen, MainScreen)
    return screen


def _status(app: VimTGApp) -> StatusLine:
    return _screen(app).query_one("#status-line", StatusLine)


def _message(app: VimTGApp) -> CommandLine:
    return _screen(app).query_one("#command-line", CommandLine)


async def _type(pilot: Any, text: str) -> None:
    for ch in text:
        await pilot.press("space" if ch == " " else ch)


def _seed_cards(cards: list[dict[str, Any]], synced_at: str) -> None:
    db = Database(db_path())
    try:
        db.initialize()
        CardRepository(db).replace_all(
            [Card.from_scryfall(d) for d in cards], synced_at=synced_at
        )
    finally:
        db.close()


# ── Offline first run ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_first_run_shows_persistent_badge(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        sl = _status(app)
        assert sl.card_data == NO_CARD_DATA
        assert sl.card_data_attention
        assert NO_CARD_DATA in sl.render().plain
        # Still there after unrelated keys (unlike a toast)
        await pilot.press("j", "k")
        assert NO_CARD_DATA in _status(app).render().plain


@pytest.mark.asyncio
async def test_search_overlay_says_why_nothing_matches(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("o")
        assert "Esc to cancel" in _message(app).message
        await _type(pilot, "bolt")
        sr = _screen(app).query_one("#search-results", SearchResults)
        assert sr.display
        assert sr.notice == OFFLINE_SEARCH_NOTICE
        assert sr.render().plain.strip() == OFFLINE_SEARCH_NOTICE
        await pilot.press("enter")
        cl = _message(app)
        # Enter no longer discards the input silently
        assert cl.message == f"Nothing added: {OFFLINE_SEARCH_NOTICE}"
        assert cl.error
        assert "bolt" not in _screen(app)._state.buffer.to_text()


@pytest.mark.asyncio
async def test_stale_card_data_is_flagged(
    tmp_path: Path, real_shape_cards: list[dict[str, Any]]
) -> None:
    _seed_cards(real_shape_cards, "2026-01-02T00:00:00+00:00")
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        sl = _status(app)
        assert sl.card_data == "card data as of 2026-01-02"
        assert sl.card_data_attention  # older than 7 days


# ── :sync ────────────────────────────────────────────────────────


def _fake_sync(cards: list[dict[str, Any]]):  # type: ignore[no-untyped-def]
    calls: list[bool] = []

    def sync(self: scryfall_sync.ScryfallSync, force: bool = False, progress: Any = None) -> int:
        calls.append(force)
        if progress:
            progress("download", 0, 0)
            progress("download", 50, 100)
            progress("download", 50, 100)  # duplicate: not re-sent to the UI
        return self._repo.replace_all(
            [Card.from_scryfall(d) for d in cards],
            synced_at=datetime.now(UTC).isoformat(),
        )

    return sync, calls


@pytest.mark.asyncio
async def test_sync_command_downloads_in_background_and_enables_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    real_shape_cards: list[dict[str, Any]],
) -> None:
    fake, calls = _fake_sync(real_shape_cards)
    monkeypatch.setattr(scryfall_sync.ScryfallSync, "sync", fake)
    progress: list[str] = []
    app = VimTGApp(deck_path=_deck(tmp_path))
    real_set = app._set_sync_progress

    def spy(text: str) -> None:
        progress.append(text)
        real_set(text)

    app._set_sync_progress = spy  # type: ignore[method-assign]
    async with app.run_test() as pilot:
        await pilot.pause()
        await _type(pilot, ":sync")
        await pilot.press("enter")
        assert _message(app).message.startswith("Syncing card data in the background")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert calls == [False]
        assert progress == ["downloading...", "downloading 50%"]
        screen = _screen(app)
        assert screen.search_service is not None
        today = datetime.now(UTC).date().isoformat()
        assert _status(app).card_data == f"card data as of {today}"
        assert not _status(app).card_data_attention
        assert not app.card_sync_running
        # Search now works
        await pilot.press("o")
        await _type(pilot, "Lightning")
        await app.workers.wait_for_complete()
        await pilot.pause()
        sr = screen.query_one("#search-results", SearchResults)
        assert sr.notice == ""
        assert any(c.name == "Lightning Bolt" for c in sr.results)


@pytest.mark.asyncio
async def test_sync_bang_forces_and_second_sync_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    real_shape_cards: list[dict[str, Any]],
) -> None:
    fake, calls = _fake_sync(real_shape_cards)
    monkeypatch.setattr(scryfall_sync.ScryfallSync, "sync", fake)
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        app._sync_running = True  # a sync is in flight
        await _type(pilot, ":sync")
        await pilot.press("enter")
        assert _message(app).message.startswith("Card sync already running")
        app._sync_running = False
        await _type(pilot, ":sync!")
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert calls == [True]


@pytest.mark.asyncio
async def test_offline_sync_failure_is_friendly_and_badge_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def offline(self: object, force: bool = False, progress: Any = None) -> int:
        raise httpx.ConnectError(
            "[Errno -3] Temporary failure in name resolution",
            request=httpx.Request("GET", scryfall_sync.BULK_DATA_URL),
        )

    for var in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(scryfall_sync.ScryfallSync, "sync", offline)
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _type(pilot, ":sync")
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        cl = _message(app)
        assert cl.error
        assert "you seem to be offline" in cl.message
        assert "run :sync to retry" in cl.message
        assert not app.card_sync_running
        assert _status(app).card_data == NO_CARD_DATA


@pytest.mark.asyncio
async def test_sync_progress_shows_in_status_line(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        app._sync_running = True
        app._set_sync_progress("downloading 42%")
        await pilot.pause()
        assert _status(app).card_data == "syncing card data downloading 42%"
        app._sync_running = False


def test_sync_progress_text() -> None:
    assert sync_progress_text("download", 42, 100) == "downloading 42%"
    assert sync_progress_text("download", 0, 0) == "downloading..."
    assert sync_progress_text("parse", 5000, 10000) == "loading 50%"
    assert sync_progress_text("download_tags", 42, 100) == "downloading tags 42%"
    assert sync_progress_text("parse_tags", 0, 0) == "loading tags..."


@pytest.mark.asyncio
async def test_finished_sync_says_when_tags_were_skipped(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        app._finish_auto_sync(42, tags_note="Scryfall unreachable")
        await pilot.pause()
        assert app.message_log[-1] == (
            False,
            "Card sync: Card database updated (42 cards); oracle tags skipped: "
            "Scryfall unreachable",
        )
        app._finish_auto_sync(42)
        await pilot.pause()
        assert app.message_log[-1] == (False, "Card sync: Card database updated (42 cards)")


# ── Corrupt database at launch ───────────────────────────────────


@pytest.mark.asyncio
async def test_corrupt_database_does_not_block_launch(tmp_path: Path) -> None:
    db_file = db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_file.write_bytes(b"definitely not sqlite " * 400)
    notes: list[tuple[str, str]] = []
    app = VimTGApp(deck_path=_deck(tmp_path))
    real_notify = app.notify

    def spy(message: str, **kwargs: Any) -> None:
        notes.append((message, str(kwargs.get("severity", ""))))
        real_notify(message, **kwargs)

    app.notify = spy  # type: ignore[method-assign]
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = _screen(app)  # the editor opened
        assert screen.card_repo is not None and screen.card_repo.count() == 0
        assert _status(app).card_data == NO_CARD_DATA
        backups = list(db_file.parent.glob("cards.db.corrupt-*"))
        assert len(backups) == 1
        warning = [m for m, sev in notes if sev == "error"]
        assert warning and "rebuilt" in warning[0] and str(backups[0]) in warning[0]
        # History works on the rebuilt file
        await _type(pilot, ':commit "after recovery"')
        await pilot.press("enter")
        assert not _message(app).error


@pytest.mark.asyncio
async def test_corrupt_card_pages_keep_deck_history(
    tmp_path: Path, real_shape_cards: list[dict[str, Any]],
) -> None:
    _seed_cards(real_shape_cards, "2026-10-01T00:00:00+00:00")
    db_file = db_path()
    conn = sqlite3.connect(db_file)
    conn.execute(
        "INSERT INTO snapshots (id, deck_path, deck_state, timestamp) "
        "VALUES ('keep', '/x.deck', '4 Shock\n', '2026-10-01')"
    )
    conn.commit()
    root = conn.execute("SELECT rootpage FROM sqlite_master WHERE name='cards'").fetchone()[0]
    size = conn.execute("PRAGMA page_size").fetchone()[0]
    conn.close()
    with open(db_file, "r+b") as f:
        f.seek((root - 1) * size)
        f.write(b"\x00\xff" * (size // 2))

    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._db is not None
        rows = app._db.connect().execute("SELECT id FROM snapshots").fetchall()
        assert [r[0] for r in rows] == ["keep"]
        assert "Deck history was recovered (1 snapshots)" in app._db_warning


# ── Paste ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_paste_into_card_search_inserts_text(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("o")
        await _type(pilot, "x")
        await pilot.press("backspace")
        app.post_message(events.Paste("Lightning\nBolt"))  # routed by the app
        await pilot.pause()
        screen = _screen(app)
        assert screen.query_one("#command-line", CommandLine).text == "Lightning Bolt"
        assert screen._state.search_query == "Lightning Bolt"
        # Typing continues after the pasted text
        await _type(pilot, "!")
        assert screen._state.search_query == "Lightning Bolt!"


@pytest.mark.asyncio
async def test_paste_into_command_line(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _type(pilot, ":import ")
        _screen(app).post_message(events.Paste("https://moxfield.com/decks/abc\n"))
        await pilot.pause()
        assert _message(app).text == "import https://moxfield.com/decks/abc"


@pytest.mark.asyncio
async def test_paste_decklist_in_normal_mode_is_one_undo_step(tmp_path: Path) -> None:
    original = "// Deck: Burn\n\n4 Goblin Guide\n"
    app = VimTGApp(deck_path=_deck(tmp_path, original))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = _screen(app)
        before = screen._state.buffer.to_text()
        screen.post_message(events.Paste(
            "4 Lightning Bolt\n2 Goblin Guide\nwhat is this\n\nSideboard\n1 Pyroblast\n"
        ))
        await pilot.pause()
        text = screen._state.buffer.to_text()
        assert "6 Goblin Guide" in text
        assert "4 Lightning Bolt" in text
        assert "SB:\n    1 Pyroblast" in text
        assert screen._state.modified
        cl = _message(app)
        assert cl.message == (
            "Pasted 7 cards (3 lines) | 1 line(s) skipped (line 3: what is this)"
        )
        await pilot.press("u")
        assert screen._state.buffer.to_text() == before


@pytest.mark.asyncio
async def test_paste_without_cards_changes_nothing(tmp_path: Path) -> None:
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = _screen(app)
        before = screen._state.buffer.to_text()
        screen.post_message(events.Paste("hello\nworld\n"))
        await pilot.pause()
        assert screen._state.buffer.to_text() == before
        assert not screen._state.modified
        assert _message(app).error
        assert "no card lines found" in _message(app).message


# ── :clipboard ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clipboard_falls_back_to_textual_osc52(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clipboard.shutil, "which", lambda _name: None)
    for var in ("SSH_TTY", "SSH_CONNECTION"):
        monkeypatch.delenv(var, raising=False)
    app = VimTGApp(deck_path=_deck(tmp_path))
    sent: list[str] = []
    app.copy_to_clipboard = sent.append  # type: ignore[method-assign]
    async with app.run_test() as pilot:
        await pilot.pause()
        await _type(pilot, ":clipboard")
        await pilot.press("enter")
        assert sent and "4 Goblin Guide" in sent[0]
        cl = _message(app)
        assert cl.message.startswith("Sent arena (")
        assert "OSC 52" in cl.message
        assert not cl.error


@pytest.mark.real_clipboard
@pytest.mark.asyncio
async def test_clipboard_native_tool_is_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    ran: list[list[str]] = []

    def fake_run(args: list[str], **_kw: Any) -> subprocess.CompletedProcess[bytes]:
        ran.append(args)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    for var in ("SSH_TTY", "SSH_CONNECTION", "DISPLAY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setattr(
        clipboard.shutil, "which", lambda n: "/usr/bin/wl-copy" if n == "wl-copy" else None
    )
    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
    app = VimTGApp(deck_path=_deck(tmp_path))
    sent: list[str] = []
    app.copy_to_clipboard = sent.append  # type: ignore[method-assign]
    async with app.run_test() as pilot:
        await pilot.pause()
        await _type(pilot, ":clipboard mtgo")
        await pilot.press("enter")
        assert ran == [["wl-copy"]]
        assert sent == []
        assert _message(app).message == "Copied mtgo (1 lines) to clipboard"


@pytest.mark.asyncio
async def test_clipboard_with_no_path_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vimtg.tui.screens import main_screen

    monkeypatch.setattr(
        main_screen, "copy_to_clipboard",
        lambda _text, osc52=None: clipboard.CopyResult(False),
    )
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _type(pilot, ":clipboard")
        await pilot.press("enter")
        cl = _message(app)
        assert cl.error
        assert cl.message.startswith("E: No clipboard available")


@pytest.mark.asyncio
async def test_search_during_the_first_sync_shows_its_progress(tmp_path: Path) -> None:
    """The download is automatic: the notice says how far it is, not
    that the user has to run :sync, and follows the progress."""
    app = VimTGApp(deck_path=_deck(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        app._sync_running = True
        app._set_sync_progress("downloading 40%")
        await pilot.press("o")
        await pilot.pause()
        cl = _message(app)
        assert cl.message.startswith(
            "Card database downloading 40%: search works when it finishes"
        )
        assert ":sync" not in cl.message
        await _type(pilot, "bolt")
        await pilot.pause()
        sr = _screen(app).query_one("#search-results", SearchResults)
        assert sr.notice == "Card database downloading 40%: search works when it finishes"
        app._set_sync_progress("loading 75%")
        await pilot.pause()
        assert sr.notice == "Card database loading 75%: search works when it finishes"
        app._sync_running = False

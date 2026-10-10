"""Persistent UI state: recent decks and the tips dismissal."""

from __future__ import annotations

from pathlib import Path

from vimtg.config import app_state
from vimtg.config.paths import state_dir


def test_recent_decks_newest_first_without_duplicates(tmp_path: Path) -> None:
    a = tmp_path / "a.deck"
    b = tmp_path / "b.deck"
    a.touch()
    b.touch()
    app_state.remember_deck(a)
    app_state.remember_deck(b)
    app_state.remember_deck(a)
    assert app_state.recent_decks() == [a.resolve(), b.resolve()]


def test_recent_decks_skips_deleted_files(tmp_path: Path) -> None:
    gone = tmp_path / "gone.deck"
    gone.touch()
    app_state.remember_deck(gone)
    gone.unlink()
    assert app_state.recent_decks() == []


def test_recent_decks_capped(tmp_path: Path) -> None:
    for i in range(app_state.MAX_RECENT + 5):
        p = tmp_path / f"{i}.deck"
        p.touch()
        app_state.remember_deck(p)
    assert len(app_state.recent_decks()) == app_state.MAX_RECENT


def test_corrupt_state_file_is_ignored(tmp_path: Path) -> None:
    (state_dir() / app_state.STATE_FILE).write_text("{not json", encoding="utf-8")
    assert app_state.recent_decks() == []
    assert app_state.tips_dismissed() is False
    deck = tmp_path / "x.deck"
    deck.touch()
    app_state.remember_deck(deck)  # rewrites a usable file
    assert app_state.recent_decks() == [deck.resolve()]


def test_tips_dismissal_persists() -> None:
    assert app_state.tips_dismissed() is False
    app_state.set_tips_dismissed(True)
    assert app_state.tips_dismissed() is True
    app_state.set_tips_dismissed(False)
    assert app_state.tips_dismissed() is False

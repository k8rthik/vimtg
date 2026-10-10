"""Crash-recovery files under $XDG_STATE_HOME/vimtg/recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.config.paths import recovery_dir
from vimtg.services.recovery import (
    discard_recovery,
    pending_recovery,
    read_recovery,
    recovery_path,
    write_recovery,
)


def test_recovery_lives_in_the_xdg_state_dir(tmp_path: Path) -> None:
    path = recovery_path(tmp_path / "burn.deck")
    assert path == recovery_dir() / "burn.deck"
    assert "vimtg" in path.parts and "recovery" in path.parts


def test_unnamed_buffer_has_a_recovery_name() -> None:
    assert recovery_path(None).name == "unnamed.deck"


def test_write_read_discard_roundtrip(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    saved = write_recovery(deck, "4 Lightning Bolt\n", "Traceback: boom")
    assert saved is not None and saved.exists()
    assert read_recovery(deck) == "4 Lightning Bolt\n"
    assert saved.with_suffix(".log").read_text() == "Traceback: boom"
    discard_recovery(deck)
    assert read_recovery(deck) is None
    assert not saved.with_suffix(".log").exists()


def test_write_failure_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(Path, "write_text", _fail)
    assert write_recovery(tmp_path / "burn.deck", "x\n") is None


def test_pending_only_when_the_copy_differs(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    assert pending_recovery(deck, "a\n") is False
    write_recovery(deck, "b\n")
    assert pending_recovery(deck, "a\n") is True
    # An identical copy is stale: removed, never offered
    assert pending_recovery(deck, "b\n") is False
    assert read_recovery(deck) is None

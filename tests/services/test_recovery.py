"""Crash-recovery files under $XDG_STATE_HOME/vimtg/recovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.config.paths import recovery_dir
from vimtg.services.recovery import (
    HEADER,
    discard_copy,
    discard_recovery,
    list_recoveries,
    new_buffer_id,
    orphaned_recoveries,
    pending_recovery,
    read_copy,
    read_recovery,
    recovery_path,
    write_recovery,
)


def test_recovery_lives_in_the_xdg_state_dir(tmp_path: Path) -> None:
    path = recovery_path(tmp_path / "burn.deck")
    assert path.parent == recovery_dir()
    assert path.name.startswith("burn.") and path.suffix == ".deck"
    assert "vimtg" in path.parts and "recovery" in path.parts


def test_same_name_in_two_directories_gets_two_copies(tmp_path: Path) -> None:
    """Regression: one/burn.deck's crash copy was offered for two/burn.deck."""
    one, two = tmp_path / "one" / "burn.deck", tmp_path / "two" / "burn.deck"
    assert recovery_path(one) != recovery_path(two)
    write_recovery(one, "4 Lightning Bolt\n")
    assert read_recovery(two) is None
    assert pending_recovery(two, "20 Mountain\n") is False
    assert read_recovery(one) == "4 Lightning Bolt\n"


def test_same_stem_different_suffix_do_not_collide(tmp_path: Path) -> None:
    assert recovery_path(tmp_path / "a.deck") != recovery_path(tmp_path / "a.txt")


def test_relative_and_absolute_paths_share_a_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert recovery_path(Path("burn.deck")) == recovery_path(tmp_path / "burn.deck")


def test_symlink_shares_its_targets_copy(tmp_path: Path) -> None:
    real = tmp_path / "burn.deck"
    real.write_text("x\n", encoding="utf-8")
    link = tmp_path / "link.deck"
    link.symlink_to(real)
    assert recovery_path(link) == recovery_path(real)


def test_discard_only_touches_this_exact_deck(tmp_path: Path) -> None:
    """Regression: :w on two/burn.deck deleted one/burn.deck's copy."""
    one, two = tmp_path / "one" / "burn.deck", tmp_path / "two" / "burn.deck"
    write_recovery(one, "one\n")
    write_recovery(two, "two\n")
    discard_recovery(two)
    assert read_recovery(one) == "one\n"
    assert read_recovery(two) is None


def test_copy_records_its_original_path(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    saved = write_recovery(deck, "4 Lightning Bolt\n")
    assert saved is not None
    first = saved.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith(HEADER)
    # JSON, so a Windows path's backslashes are escaped: decode, don't grep
    assert json.loads(first[len(HEADER):]) == {"path": str(deck.resolve())}
    # The header is never part of the recovered text
    assert read_recovery(deck) == "4 Lightning Bolt\n"
    assert read_copy(saved) == "4 Lightning Bolt\n"


def test_a_copy_recording_another_path_is_not_handed_out(tmp_path: Path) -> None:
    mine, other = tmp_path / "mine.deck", tmp_path / "other.deck"
    write_recovery(other, "other\n")
    # Simulate a key collision: other's copy sitting at mine's key
    recovery_path(other).rename(recovery_path(mine))
    assert read_recovery(mine) is None


def test_unnamed_buffers_get_their_own_copies() -> None:
    a, b = new_buffer_id(), new_buffer_id()
    assert a != b
    assert recovery_path(None, a) != recovery_path(None, b)
    write_recovery(None, "a\n", buffer_id=a)
    write_recovery(None, "b\n", buffer_id=b)
    assert read_recovery(None, a) == "a\n"
    assert read_recovery(None, b) == "b\n"


def test_unnamed_buffer_without_an_id_has_a_fallback_name() -> None:
    assert recovery_path(None).name == "unnamed.deck"


def test_write_read_discard_roundtrip(tmp_path: Path) -> None:
    deck = tmp_path / "burn.deck"
    saved = write_recovery(deck, "4 Lightning Bolt\n", "Traceback: boom")
    assert saved is not None and saved.exists()
    assert read_recovery(deck) == "4 Lightning Bolt\n"
    assert saved.with_suffix(".log").read_text(encoding="utf-8") == "Traceback: boom"
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


def test_list_and_orphans(tmp_path: Path) -> None:
    alive = tmp_path / "alive.deck"
    alive.write_text("x\n", encoding="utf-8")
    gone = tmp_path / "gone.deck"
    buffer_id = new_buffer_id()
    write_recovery(alive, "alive\n")
    write_recovery(gone, "gone\n")
    write_recovery(None, "unnamed\n", buffer_id=buffer_id)
    # A copy from before the header existed still lists (as unnamed)
    (recovery_dir() / "legacy.deck").write_text("legacy\n", encoding="utf-8")

    listed = {c.copy: c for c in list_recoveries()}
    assert len(listed) == 4
    orphans = {c.copy for c in orphaned_recoveries()}
    assert recovery_path(alive) not in orphans
    assert recovery_path(gone) in orphans
    assert recovery_path(None, buffer_id) in orphans
    assert recovery_dir() / "legacy.deck" in orphans

    unnamed = listed[recovery_path(None, buffer_id)]
    assert unnamed.original is None and unnamed.buffer_id == buffer_id
    assert unnamed.label == "(unnamed buffer)"
    named = listed[recovery_path(gone)]
    assert named.original == gone.resolve() and named.buffer_id is None
    assert named.label == "gone.deck"

    discard_copy(recovery_path(gone))
    assert recovery_path(gone) not in {c.copy for c in list_recoveries()}


def test_list_skips_unreadable_copies() -> None:
    (recovery_dir() / "bad.deck").write_bytes(b"\xff\xfe\x00bad")
    assert all(c.copy.name != "bad.deck" for c in list_recoveries())


def test_undecodable_bytes_in_the_deck_path_do_not_raise(tmp_path: Path) -> None:
    # A file name the filesystem could not decode arrives with surrogate
    # escapes; "never raises" helpers must still never raise for it
    deck = tmp_path / "caf\udce9.deck"
    path = recovery_path(deck)
    assert path.parent == recovery_dir()
    assert pending_recovery(deck, "") is False
    discard_recovery(deck)

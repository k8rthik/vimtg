"""Tests for atomic_write_text and FileStamp (data.file_io)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from vimtg.data import file_io
from vimtg.data.deck_repository import DeckRepository
from vimtg.data.file_io import ABSENT, atomic_write_text, file_stamp

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX permissions/symlinks")


class TestAtomicWrite:
    def test_writes_new_file(self, tmp_path: Path) -> None:
        target = tmp_path / "a.deck"
        assert atomic_write_text(target, "4 Lightning Bolt\n") == target
        assert target.read_text(encoding="utf-8") == "4 Lightning Bolt\n"

    @posix_only
    def test_symlink_is_kept_and_its_target_rewritten(self, tmp_path: Path) -> None:
        real = tmp_path / "real.deck"
        real.write_text("old\n", encoding="utf-8")
        link = tmp_path / "link.deck"
        link.symlink_to(real)

        atomic_write_text(link, "new\n")

        assert link.is_symlink()
        assert real.read_text(encoding="utf-8") == "new\n"

    @posix_only
    def test_existing_mode_preserved(self, tmp_path: Path) -> None:
        target = tmp_path / "shared.deck"
        target.write_text("old\n", encoding="utf-8")
        target.chmod(0o644)

        atomic_write_text(target, "new\n")

        assert stat.S_IMODE(target.stat().st_mode) == 0o644

    @posix_only
    def test_new_file_honors_umask_not_mkstemp_0600(self, tmp_path: Path) -> None:
        old = os.umask(0o022)
        try:
            atomic_write_text(tmp_path / "n.deck", "x\n")
        finally:
            os.umask(old)
        assert stat.S_IMODE((tmp_path / "n.deck").stat().st_mode) == 0o644

    def test_file_and_directory_fsynced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[int] = []
        real_fsync = os.fsync
        monkeypatch.setattr(os, "fsync", lambda fd: (calls.append(fd), real_fsync(fd)))
        atomic_write_text(tmp_path / "f.deck", "x\n")
        expected = 2 if os.name == "posix" else 1
        assert len(calls) == expected

    def test_failed_replace_leaves_original_and_no_temp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "keep.deck"
        target.write_text("original\n", encoding="utf-8")

        def boom(src: object, dst: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(file_io.os, "replace", boom)
        with pytest.raises(OSError, match="disk full"):
            atomic_write_text(target, "new\n")
        assert target.read_text(encoding="utf-8") == "original\n"
        assert [p.name for p in tmp_path.iterdir()] == ["keep.deck"]

    @posix_only
    def test_deck_repository_save_uses_helper(self, tmp_path: Path) -> None:
        real = tmp_path / "real.deck"
        real.write_text("old\n", encoding="utf-8")
        real.chmod(0o640)
        link = tmp_path / "link.deck"
        link.symlink_to(real)

        DeckRepository().save(link, "new\n")

        assert link.is_symlink()
        assert real.read_text(encoding="utf-8") == "new\n"
        assert stat.S_IMODE(real.stat().st_mode) == 0o640


class TestFileStamp:
    def test_missing_file_is_absent(self, tmp_path: Path) -> None:
        assert file_stamp(tmp_path / "nope") == ABSENT

    def test_changes_when_content_changes(self, tmp_path: Path) -> None:
        p = tmp_path / "s.deck"
        p.write_text("a\n", encoding="utf-8")
        before = file_stamp(p)
        assert file_stamp(p) == before
        p.write_text("a longer body\n", encoding="utf-8")
        assert file_stamp(p) != before

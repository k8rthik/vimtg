"""Tests for atomic_write_text and FileStamp (data.file_io)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from vimtg.data import file_io
from vimtg.data.deck_repository import DeckRepository
from vimtg.data.file_io import (
    ABSENT,
    CHANGED,
    CREATED,
    DELETED,
    FileStamp,
    atomic_write_text,
    disk_change,
    file_stamp,
)

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


class TestDiskChange:
    """disk_change compares content, so it catches what mtime+size miss
    and ignores what they flag needlessly."""

    def test_unchanged(self, tmp_path: Path) -> None:
        p = tmp_path / "s.deck"
        p.write_text("a\n", encoding="utf-8")
        assert disk_change(p, file_stamp(p)) is None

    def test_same_size_same_mtime_rewrite_is_a_change(self, tmp_path: Path) -> None:
        p = tmp_path / "s.deck"
        p.write_text("abc\n", encoding="utf-8")
        st = p.stat()
        stamp = file_stamp(p)
        p.write_text("xyz\n", encoding="utf-8")
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
        assert (file_stamp(p).mtime_ns, file_stamp(p).size) == (stamp.mtime_ns, stamp.size)
        assert disk_change(p, stamp) == CHANGED

    def test_touch_is_not_a_change(self, tmp_path: Path) -> None:
        p = tmp_path / "s.deck"
        p.write_text("abc\n", encoding="utf-8")
        stamp = file_stamp(p)
        os.utime(p, ns=(stamp.mtime_ns + 10**9, stamp.mtime_ns + 10**9))
        assert disk_change(p, stamp) is None

    def test_deleted_and_created(self, tmp_path: Path) -> None:
        p = tmp_path / "s.deck"
        p.write_text("abc\n", encoding="utf-8")
        stamp = file_stamp(p)
        p.unlink()
        assert disk_change(p, stamp) == DELETED
        assert disk_change(p, ABSENT) is None
        p.write_text("new\n", encoding="utf-8")
        assert disk_change(p, ABSENT) == CREATED

    def test_stamp_without_digest_falls_back_to_mtime_and_size(
        self, tmp_path: Path
    ) -> None:
        p = tmp_path / "s.deck"
        p.write_text("abc\n", encoding="utf-8")
        st = p.stat()
        legacy = FileStamp(mtime_ns=st.st_mtime_ns, size=st.st_size)
        assert disk_change(p, legacy) is None
        p.write_text("abcdef\n", encoding="utf-8")
        assert disk_change(p, legacy) == CHANGED

    def test_unreadable_file_has_no_digest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        p = tmp_path / "s.deck"
        p.write_text("abc\n", encoding="utf-8")

        def _deny(_self: Path) -> bytes:
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "read_bytes", _deny)
        assert file_stamp(p).digest == ""

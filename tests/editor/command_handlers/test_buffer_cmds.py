"""Tests for buffer commands: :w, :q, :wq."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.data.file_io import ABSENT, file_stamp
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.buffer_cmds import (
    cmd_home,
    cmd_quit,
    cmd_write,
    cmd_write_quit,
)
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _make_cmd(name: str = "w", args: str = "", bang: bool = False) -> ParsedCommand:
    return ParsedCommand(name=name, args=args, bang=bang)


def _sample_buffer() -> Buffer:
    return Buffer.from_text("4 Lightning Bolt\n2 Counterspell\n")


def _noop_save(path: Path, text: str) -> None:
    """A no-op save function for testing."""


class TestCmdWrite:
    def test_write_calls_save_fn(self, tmp_path: Path) -> None:
        saved: list[tuple[Path, str]] = []

        def capture_save(p: Path, t: str) -> None:
            saved.append((p, t))

        buf = _sample_buffer()
        fp = tmp_path / "test.deck"
        ctx = EditorContext(file_path=fp, modified=True, save_fn=capture_save)
        new_buf, _ = cmd_write(buf, Cursor(), _make_cmd("w"), ctx)
        assert len(saved) == 1
        assert saved[0][0] == fp
        assert saved[0][1] == buf.to_text()
        assert "Written" in ctx.message
        assert ctx.modified is False
        assert new_buf is buf

    def test_write_with_filename_arg(self) -> None:
        saved: list[tuple[Path, str]] = []

        def capture_save(p: Path, t: str) -> None:
            saved.append((p, t))

        buf = _sample_buffer()
        ctx = EditorContext(file_path=None, modified=True, save_fn=capture_save)
        cmd_write(buf, Cursor(), _make_cmd("w", args="myfile"), ctx)
        assert len(saved) == 1
        assert saved[0][0].name == "myfile.deck"
        assert ctx.file_path is not None
        assert ctx.file_path.name == "myfile.deck"
        assert ctx.error is False

    def test_write_with_filename_arg_preserves_extension(self) -> None:
        saved: list[tuple[Path, str]] = []

        def capture_save(p: Path, t: str) -> None:
            saved.append((p, t))

        buf = _sample_buffer()
        ctx = EditorContext(save_fn=capture_save)
        cmd_write(buf, Cursor(), _make_cmd("w", args="my.deck"), ctx)
        assert saved[0][0].name == "my.deck"

    def test_write_no_path_generates_slug(self) -> None:
        saved: list[tuple[Path, str]] = []

        def capture_save(p: Path, t: str) -> None:
            saved.append((p, t))

        buf = _sample_buffer()
        ctx = EditorContext(file_path=None, modified=True, save_fn=capture_save)
        cmd_write(buf, Cursor(), _make_cmd("w"), ctx)
        assert len(saved) == 1
        assert saved[0][0].suffix == ".deck"
        assert ctx.file_path == saved[0][0]
        assert ctx.error is False
        assert "Written" in ctx.message

    def test_write_no_path_names_file_after_deck(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A new deck's first :w is named from '// Deck:', not a random slug."""
        monkeypatch.chdir(tmp_path)
        saved: list[Path] = []
        buf = Buffer.from_text("// Deck: Mono-Red Burn!\n// Format: modern\n\n4 Lightning Bolt\n")
        ctx = EditorContext(save_fn=lambda p, t: saved.append(p))
        cmd_write(buf, Cursor(), _make_cmd("w"), ctx)
        assert saved == [tmp_path / "mono-red-burn.deck"]
        assert ctx.file_path == tmp_path / "mono-red-burn.deck"

    def test_write_deck_name_never_collides(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "burn.deck").write_text("keep me\n", encoding="utf-8")
        saved: list[Path] = []
        buf = Buffer.from_text("// Deck: Burn\n\n4 Lightning Bolt\n")
        ctx = EditorContext(save_fn=lambda p, t: saved.append(p))
        cmd_write(buf, Cursor(), _make_cmd("w"), ctx)
        assert saved == [tmp_path / "burn-2.deck"]
        assert ctx.error is False

    def test_write_unnamed_deck_falls_back_to_random_slug(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        saved: list[Path] = []
        buf = Buffer.from_text("// Deck:\n\n4 Lightning Bolt\n")
        ctx = EditorContext(save_fn=lambda p, t: saved.append(p))
        cmd_write(buf, Cursor(), _make_cmd("w"), ctx)
        assert saved[0].name.endswith("-deck.deck")

    def test_write_no_save_fn_errors(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(file_path=Path("/tmp/test.deck"), save_fn=None)
        cmd_write(buf, Cursor(), _make_cmd("w"), ctx)
        assert "Save not available" in ctx.message
        assert ctx.error is True

    def test_write_error_propagates(self, tmp_path: Path) -> None:
        def failing_save(p: Path, t: str) -> None:
            raise OSError("disk full")

        buf = _sample_buffer()
        ctx = EditorContext(
            file_path=tmp_path / "test.deck", save_fn=failing_save,
        )
        cmd_write(buf, Cursor(), _make_cmd("w"), ctx)
        assert "Write failed" in ctx.message
        assert ctx.error is True

    def test_write_clears_modified_flag(self, tmp_path: Path) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(
            file_path=tmp_path / "test.deck",
            modified=True,
            save_fn=_noop_save,
        )
        cmd_write(buf, Cursor(), _make_cmd("w"), ctx)
        assert ctx.modified is False

    def test_write_sets_file_path_on_ctx(self, tmp_path: Path) -> None:
        """After :w, ctx.file_path points to the saved file."""
        fp = tmp_path / "out.deck"
        buf = _sample_buffer()
        ctx = EditorContext(file_path=fp, modified=True, save_fn=_noop_save)
        cmd_write(buf, Cursor(), _make_cmd("w"), ctx)
        assert ctx.file_path == fp


class TestCmdQuit:
    def test_quit_unmodified(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(modified=False)
        cmd_quit(buf, Cursor(), _make_cmd("q"), ctx)
        assert ctx.quit_requested is True

    def test_quit_modified_no_bang(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(modified=True)
        cmd_quit(buf, Cursor(), _make_cmd("q", bang=False), ctx)
        assert ctx.quit_requested is False
        assert "Unsaved changes" in ctx.message
        assert ctx.error is True

    def test_quit_modified_bang(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(modified=True)
        cmd_quit(buf, Cursor(), _make_cmd("q", bang=True), ctx)
        assert ctx.quit_requested is True


class TestCmdWriteQuit:
    def test_write_quit_delegates_and_quits(self, tmp_path: Path) -> None:
        saved: list[tuple[Path, str]] = []

        def capture_save(p: Path, t: str) -> None:
            saved.append((p, t))

        buf = _sample_buffer()
        fp = tmp_path / "test.deck"
        ctx = EditorContext(file_path=fp, modified=True, save_fn=capture_save)
        cmd_write_quit(buf, Cursor(), _make_cmd("wq"), ctx)
        assert ctx.quit_requested is True
        assert ctx.modified is False
        assert "Written" in ctx.message
        assert len(saved) == 1

    def test_write_quit_no_quit_on_error(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(file_path=None, save_fn=None)
        cmd_write_quit(buf, Cursor(), _make_cmd("wq"), ctx)
        assert ctx.quit_requested is False
        assert ctx.error is True

    def test_write_quit_no_save_fn_errors(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(file_path=Path("/tmp/test.deck"), save_fn=None)
        cmd_write_quit(buf, Cursor(), _make_cmd("wq"), ctx)
        assert ctx.quit_requested is False
        assert ctx.error is True


class TestCmdHome:
    def test_home_unmodified(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(modified=False)
        cmd_home(buf, Cursor(), _make_cmd("home"), ctx)
        assert ctx.greeter_requested is True

    def test_home_modified_no_bang(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(modified=True)
        cmd_home(buf, Cursor(), _make_cmd("home", bang=False), ctx)
        assert ctx.greeter_requested is False
        assert "Unsaved changes" in ctx.message
        assert ctx.error is True

    def test_home_modified_bang(self) -> None:
        buf = _sample_buffer()
        ctx = EditorContext(modified=True)
        cmd_home(buf, Cursor(), _make_cmd("home", bang=True), ctx)
        assert ctx.greeter_requested is True


class TestWriteSafety:
    """:w must not silently clobber other files or outside changes."""

    @staticmethod
    def _real_save(p: Path, t: str) -> None:
        p.write_text(t, encoding="utf-8")

    def test_write_other_existing_file_is_e13(self, tmp_path: Path) -> None:
        other = tmp_path / "other.deck"
        other.write_text("precious\n", encoding="utf-8")
        ctx = EditorContext(
            file_path=tmp_path / "mine.deck", modified=True, save_fn=self._real_save,
        )
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w", args=str(other)), ctx)
        assert ctx.error is True
        assert "E13" in ctx.message
        assert other.read_text(encoding="utf-8") == "precious\n"
        assert ctx.file_path == tmp_path / "mine.deck"
        assert ctx.modified is True

    def test_bang_overwrites_other_file(self, tmp_path: Path) -> None:
        other = tmp_path / "other.deck"
        other.write_text("precious\n", encoding="utf-8")
        ctx = EditorContext(save_fn=self._real_save)
        cmd_write(
            _sample_buffer(), Cursor(), _make_cmd("w", args=str(other), bang=True), ctx,
        )
        assert ctx.error is False
        assert other.read_text(encoding="utf-8") == _sample_buffer().to_text()
        # :w name works like vim's :saveas — the buffer is now bound to it
        assert ctx.file_path == other

    def test_write_own_name_explicitly_is_not_e13(self, tmp_path: Path) -> None:
        mine = tmp_path / "mine.deck"
        mine.write_text("old\n", encoding="utf-8")
        ctx = EditorContext(file_path=mine, save_fn=self._real_save)
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w", args=str(mine)), ctx)
        assert ctx.error is False

    def test_tilde_expanded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        saved: list[Path] = []
        ctx = EditorContext(save_fn=lambda p, t: saved.append(p))
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w", args="~/burn"), ctx)
        assert saved == [tmp_path / "burn.deck"]

    def test_changed_on_disk_refused(self, tmp_path: Path) -> None:
        mine = tmp_path / "mine.deck"
        mine.write_text("as read\n", encoding="utf-8")
        stamp = file_stamp(mine)
        mine.write_text("someone else's edit\n", encoding="utf-8")
        ctx = EditorContext(
            file_path=mine, modified=True, save_fn=self._real_save, disk_stamp=stamp,
        )
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w"), ctx)
        assert ctx.error is True
        assert "changed on disk" in ctx.message
        assert mine.read_text(encoding="utf-8") == "someone else's edit\n"

        forced = EditorContext(file_path=mine, save_fn=self._real_save, disk_stamp=stamp)
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w", bang=True), forced)
        assert forced.error is False
        assert mine.read_text(encoding="utf-8") == _sample_buffer().to_text()

    def test_unchanged_file_saves_and_restamps(self, tmp_path: Path) -> None:
        mine = tmp_path / "mine.deck"
        mine.write_text("as read\n", encoding="utf-8")
        ctx = EditorContext(
            file_path=mine, save_fn=self._real_save, disk_stamp=file_stamp(mine),
        )
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w"), ctx)
        assert ctx.error is False
        assert ctx.disk_stamp == file_stamp(mine)
        # A second :w right after is not a "change on disk"
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w"), ctx)
        assert ctx.error is False

    def test_new_file_that_appeared_before_first_write(self, tmp_path: Path) -> None:
        mine = tmp_path / "new.deck"
        ctx = EditorContext(file_path=mine, save_fn=self._real_save, disk_stamp=ABSENT)
        mine.write_text("created elsewhere\n", encoding="utf-8")
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w"), ctx)
        assert ctx.error is True
        assert mine.read_text(encoding="utf-8") == "created elsewhere\n"

    def test_new_file_first_write(self, tmp_path: Path) -> None:
        mine = tmp_path / "new.deck"
        ctx = EditorContext(file_path=mine, save_fn=self._real_save, disk_stamp=ABSENT)
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w"), ctx)
        assert ctx.error is False
        assert mine.exists()

    def test_wq_does_not_quit_on_conflict(self, tmp_path: Path) -> None:
        other = tmp_path / "other.deck"
        other.write_text("x\n", encoding="utf-8")
        ctx = EditorContext(save_fn=self._real_save)
        cmd_write_quit(_sample_buffer(), Cursor(), _make_cmd("wq", args=str(other)), ctx)
        assert ctx.error is True
        assert ctx.quit_requested is False

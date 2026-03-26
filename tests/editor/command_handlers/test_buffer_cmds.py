"""Tests for buffer commands: :w, :q, :wq."""

from __future__ import annotations

from pathlib import Path

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

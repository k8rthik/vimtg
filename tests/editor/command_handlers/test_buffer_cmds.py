"""Tests for buffer commands: :w, :q, :wq."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.data.file_io import ABSENT, file_stamp
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.buffer_cmds import (
    cmd_home,
    cmd_quit,
    cmd_saveas,
    cmd_write,
    cmd_write_quit,
    cmd_xit,
    register_buffer_commands,
)
from vimtg.editor.commands import CommandRegistry, EditorContext, ParsedCommand, parse_command
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


class TestWriteTargetErrors:
    @pytest.mark.parametrize("arg", ["sub/", "sub"])
    def test_directory_argument_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arg: str
    ) -> None:
        # ':w sub/' used to write a hidden 'sub/.deck' and switch to it
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sub").mkdir()
        saved: list[Path] = []
        ctx = EditorContext(
            file_path=None, modified=True, save_fn=lambda p, t: saved.append(p),
        )
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w", arg), ctx)
        assert saved == []
        assert ctx.error and "E502" in ctx.message
        assert ctx.file_path is None and ctx.modified

    def test_failure_names_the_target_not_a_temp_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from vimtg.data.deck_repository import DeckRepository

        monkeypatch.chdir(tmp_path)
        ctx = EditorContext(
            file_path=None, modified=True, save_fn=DeckRepository().save,
        )
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w", "nodir/x"), ctx)
        assert ctx.error
        target = Path.cwd() / "nodir" / "x.deck"
        assert ctx.message == f"E: Write failed: {target}: No such file or directory"
        assert ctx.modified


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


class TestDataSafetyCommands:
    @staticmethod
    def _real_save(p: Path, t: str) -> None:
        p.write_text(t, encoding="utf-8")

    def test_x_unmodified_quits_without_writing(self, tmp_path: Path) -> None:
        saved: list[Path] = []
        ctx = EditorContext(
            file_path=tmp_path / "mine.deck", save_fn=lambda p, t: saved.append(p),
        )
        cmd_xit(_sample_buffer(), Cursor(), _make_cmd("x"), ctx)
        assert ctx.quit_requested and not ctx.error
        assert saved == [] and not ctx.file_saved

    def test_x_modified_writes_then_quits(self, tmp_path: Path) -> None:
        saved: list[Path] = []
        ctx = EditorContext(
            file_path=tmp_path / "mine.deck", modified=True,
            save_fn=lambda p, t: saved.append(p),
        )
        cmd_xit(_sample_buffer(), Cursor(), _make_cmd("x"), ctx)
        assert ctx.quit_requested and saved == [tmp_path / "mine.deck"]

    def test_x_with_a_name_always_writes(self, tmp_path: Path) -> None:
        saved: list[Path] = []
        ctx = EditorContext(save_fn=lambda p, t: saved.append(p))
        cmd_xit(_sample_buffer(), Cursor(), _make_cmd("x", args=str(tmp_path / "n")), ctx)
        assert saved == [tmp_path / "n.deck"]

    def test_write_to_a_new_name_writes_a_copy(self, tmp_path: Path) -> None:
        """vim's :w {file}: the copy is written, the buffer keeps its file
        and its modified flag."""
        old = tmp_path / "old.deck"
        ctx = EditorContext(file_path=old, modified=True, save_fn=self._real_save)
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w", args=str(tmp_path / "new")), ctx)
        assert (tmp_path / "new.deck").read_text(encoding="utf-8") == _sample_buffer().to_text()
        assert ctx.file_path == old and not old.exists()
        assert ctx.modified and not ctx.file_saved
        assert ctx.message == '"new.deck" written'

    def test_an_unnamed_buffer_takes_the_name(self, tmp_path: Path) -> None:
        ctx = EditorContext(modified=True, save_fn=self._real_save)
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w", args=str(tmp_path / "new")), ctx)
        assert ctx.file_path == tmp_path / "new.deck"
        assert ctx.file_saved and not ctx.modified

    def test_saveas_switches_to_the_new_name(self, tmp_path: Path) -> None:
        ctx = EditorContext(file_path=tmp_path / "old.deck", save_fn=self._real_save)
        cmd_saveas(_sample_buffer(), Cursor(), _make_cmd("saveas", args=str(tmp_path / "new")), ctx)
        assert "now editing new.deck" in ctx.message and "old.deck" in ctx.message
        assert ctx.file_path == tmp_path / "new.deck"

    def test_write_to_own_file_is_not_a_switch(self, tmp_path: Path) -> None:
        mine = tmp_path / "mine.deck"
        ctx = EditorContext(file_path=mine, save_fn=self._real_save)
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w", args=str(mine)), ctx)
        assert ctx.message == "Written: mine.deck"

    def test_saveas(self, tmp_path: Path) -> None:
        ctx = EditorContext(file_path=tmp_path / "old.deck", save_fn=self._real_save)
        cmd_saveas(_sample_buffer(), Cursor(), _make_cmd("saveas", args=str(tmp_path / "n")), ctx)
        assert ctx.file_path == tmp_path / "n.deck" and ctx.file_saved
        empty = EditorContext(save_fn=self._real_save)
        cmd_saveas(_sample_buffer(), Cursor(), _make_cmd("saveas"), empty)
        assert empty.error and "E471" in empty.message

    def test_deleted_file_message(self, tmp_path: Path) -> None:
        mine = tmp_path / "mine.deck"
        mine.write_text("as read\n", encoding="utf-8")
        stamp = file_stamp(mine)
        mine.unlink()
        ctx = EditorContext(file_path=mine, modified=True, save_fn=self._real_save,
                            disk_stamp=stamp)
        cmd_write(_sample_buffer(), Cursor(), _make_cmd("w"), ctx)
        assert ctx.error and "no longer exists" in ctx.message
        assert "changed on disk" not in ctx.message
        assert not mine.exists()

    def test_quit_bang_and_home_bang_request_a_discard(self) -> None:
        for handler, name in ((cmd_quit, "q"), (cmd_home, "home")):
            ctx = EditorContext(modified=True)
            handler(_sample_buffer(), Cursor(), _make_cmd(name, bang=True), ctx)
            assert ctx.discard_requested
            plain = EditorContext(modified=False)
            handler(_sample_buffer(), Cursor(), _make_cmd(name), plain)
            assert not plain.discard_requested


class TestWriteQuitToACopy:
    def test_wq_name_writes_the_copy_but_keeps_the_unsaved_deck(self, tmp_path: Path) -> None:
        ctx = EditorContext(
            file_path=tmp_path / "mine.deck", modified=True,
            save_fn=lambda p, t: p.write_text(t, encoding="utf-8"),
        )
        cmd_write_quit(_sample_buffer(), Cursor(), _make_cmd("wq", args=str(tmp_path / "c")), ctx)
        assert (tmp_path / "c.deck").exists()
        assert ctx.error and "E37" in ctx.message
        assert not ctx.quit_requested

    def test_a_clean_deck_quits_after_the_copy(self, tmp_path: Path) -> None:
        ctx = EditorContext(
            file_path=tmp_path / "mine.deck",
            save_fn=lambda p, t: p.write_text(t, encoding="utf-8"),
        )
        cmd_write_quit(_sample_buffer(), Cursor(), _make_cmd("wq", args=str(tmp_path / "c")), ctx)
        assert ctx.quit_requested


def _registry() -> CommandRegistry:
    registry = CommandRegistry()
    register_buffer_commands(registry)
    return registry


def _run(text: str, ctx: EditorContext) -> None:
    _registry().execute(parse_command(text, 0, 1), _sample_buffer(), Cursor(), ctx)


class TestWindowsAndAll:
    def test_q_with_a_pane_open_closes_the_pane(self) -> None:
        ctx = EditorContext(modified=True, pane_open=True)
        _run("q", ctx)
        assert ctx.split_close and not ctx.quit_requested and not ctx.error

    def test_wq_and_x_with_a_pane_close_it_after_writing(self, tmp_path: Path) -> None:
        for command in ("wq", "x"):
            saved: list[Path] = []
            ctx = EditorContext(
                file_path=tmp_path / "m.deck", modified=True, pane_open=True,
                save_fn=lambda p, t, saved=saved: saved.append(p),
            )
            _run(command, ctx)
            assert saved and ctx.split_close and not ctx.quit_requested, command

    @pytest.mark.parametrize("command", ["qa", "qall", "quitall"])
    def test_qa_quits_past_the_pane_but_guards_changes(self, command: str) -> None:
        ctx = EditorContext(modified=True, pane_open=True)
        _run(command, ctx)
        assert ctx.error and not ctx.quit_requested
        forced = EditorContext(modified=True, pane_open=True)
        _run(f"{command}!", forced)
        assert forced.quit_requested and forced.discard_requested

    @pytest.mark.parametrize("command", ["wa", "wall"])
    def test_wa_writes_only_a_changed_deck(self, tmp_path: Path, command: str) -> None:
        saved: list[Path] = []
        clean = EditorContext(file_path=tmp_path / "m.deck", save_fn=lambda p, t: saved.append(p))
        _run(command, clean)
        assert saved == [] and not clean.error
        dirty = EditorContext(
            file_path=tmp_path / "m.deck", modified=True, save_fn=lambda p, t: saved.append(p),
        )
        _run(command, dirty)
        assert saved == [tmp_path / "m.deck"] and dirty.file_saved

    @pytest.mark.parametrize("command", ["wqa", "wqall", "xa", "xall"])
    def test_wqa_writes_and_quits(self, tmp_path: Path, command: str) -> None:
        saved: list[Path] = []
        ctx = EditorContext(
            file_path=tmp_path / "m.deck", modified=True, pane_open=True,
            save_fn=lambda p, t: saved.append(p),
        )
        _run(command, ctx)
        assert saved == [tmp_path / "m.deck"] and ctx.quit_requested

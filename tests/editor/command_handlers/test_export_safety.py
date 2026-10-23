""":export never destroys a file by accident, :export vimtg is lossless,
a bare :export copies to the clipboard, and :import lays a foreign
deck out like a new one."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.export_cmds import cmd_export, cmd_import
from vimtg.editor.commands import EditorContext, NewBuffer, ParsedCommand, parse_command
from vimtg.editor.cursor import Cursor

_DECK = (
    "// Deck: Burn\n"
    "// Format: modern\n"
    "\n"
    "// Creatures\n"
    "4 Goblin Guide  @aggro\n"
    "\n"
    "DCK:\n"
    "    4 Lightning Bolt\n"
    "    4 Fire // Ice\n"
    "\n"
    "SB:\n"
    "    2 Smash to Smithereens\n"
)


def _export(args: str, ctx: EditorContext, *, bang: bool = False) -> None:
    cmd_export(
        Buffer.from_text(_DECK), Cursor(), ParsedCommand("export", args, bang=bang), ctx
    )


class TestExportOverwrite:
    def test_refuses_existing_file_without_bang(self, tmp_path: Path) -> None:
        target = tmp_path / "list.txt"
        target.write_text("keep me\n", encoding="utf-8")
        ctx = EditorContext()
        _export(f"mtgo {target}", ctx)
        assert ctx.error and "E13" in ctx.message
        assert target.read_text(encoding="utf-8") == "keep me\n"

    def test_bang_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "list.txt"
        target.write_text("old\n", encoding="utf-8")
        ctx = EditorContext()
        _export(f"mtgo {target}", ctx, bang=True)
        assert not ctx.error
        assert "4 Lightning Bolt" in target.read_text(encoding="utf-8")

    def test_bang_parses_from_the_command_line(self) -> None:
        cmd = parse_command("export! mtgo out.txt", 0, 1)
        assert cmd.name == "export" and cmd.bang and cmd.args == "mtgo out.txt"

    @pytest.mark.parametrize("bang", [False, True])
    def test_never_writes_over_the_open_deck(self, tmp_path: Path, bang: bool) -> None:
        deck = tmp_path / "burn.deck"
        deck.write_text(_DECK, encoding="utf-8")
        ctx = EditorContext(file_path=deck)
        _export(f"mtgo {deck}", ctx, bang=bang)
        assert ctx.error and "open deck" in ctx.message
        assert deck.read_text(encoding="utf-8") == _DECK

    def test_open_deck_refused_by_relative_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        deck = tmp_path / "burn.deck"
        deck.write_text(_DECK, encoding="utf-8")
        ctx = EditorContext(file_path=deck)
        _export("mtgo burn.deck", ctx, bang=True)
        assert ctx.error
        assert deck.read_text(encoding="utf-8") == _DECK

    def test_tilde_is_expanded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows ~
        ctx = EditorContext()
        _export("arena ~/arena.txt", ctx)
        assert not ctx.error
        assert (tmp_path / "arena.txt").is_file()
        assert not Path("~").exists()

    def test_new_file_written_atomically_no_temp_left(self, tmp_path: Path) -> None:
        ctx = EditorContext()
        _export(f"arena {tmp_path / 'a.txt'}", ctx)
        assert sorted(p.name for p in tmp_path.iterdir()) == ["a.txt"]


class TestExportVimtgLossless:
    def test_vimtg_export_is_the_buffer_verbatim(self, tmp_path: Path) -> None:
        target = tmp_path / "copy.deck"
        ctx = EditorContext()
        _export(f"vimtg {target}", ctx)
        assert target.read_text(encoding="utf-8") == _DECK


class TestBareExportCopies:
    def test_bare_export_goes_to_clipboard(self) -> None:
        ctx = EditorContext()
        _export("arena", ctx)
        assert not ctx.error
        assert ctx.clipboard_text is not None
        assert "4 Lightning Bolt" in ctx.clipboard_text.splitlines()
        assert ctx.clipboard_label.startswith("arena export (")


def _imported(ctx: EditorContext) -> NewBuffer:
    assert ctx.new_buffer is not None and ctx.new_buffer.text is not None
    return ctx.new_buffer


class TestImportStructured:
    def test_foreign_import_gets_metadata_blocks_and_format_note(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "burn.txt"
        src.write_text("4 Lightning Bolt\n20 Mountain\n\n2 Duress\n", encoding="utf-8")
        ctx = EditorContext()
        cmd_import(Buffer.from_text(""), Cursor(), ParsedCommand("import", str(src)), ctx)
        new_buf = _imported(ctx)
        assert new_buf.text == (
            "// Deck: burn\n"
            "// Format:\n"
            "\n"
            "DCK:\n"
            "    4 Lightning Bolt\n"
            "    20 Mountain\n"
            "\n"
            "SB:\n"
            "    2 Duress\n"
        )
        assert "// Format:" in new_buf.message and not ctx.error

    def test_vimtg_import_keeps_the_file_layout(self, tmp_path: Path) -> None:
        src = tmp_path / "other.deck"
        src.write_text(_DECK, encoding="utf-8")
        ctx = EditorContext()
        cmd_import(Buffer.from_text(""), Cursor(), ParsedCommand("import", str(src)), ctx)
        new_buf = _imported(ctx)
        assert new_buf.text == _DECK
        assert "Format" not in new_buf.message  # it names one

    def test_import_normalises_names_and_groups_by_type(
        self, tmp_path: Path, real_shape_repo: CardRepository
    ) -> None:
        src = tmp_path / "list.txt"
        src.write_text("4 Fire/Ice\n4 fire // ice\n4 Stomp\n", encoding="utf-8")
        ctx = EditorContext(card_repo=real_shape_repo)
        cmd_import(Buffer.from_text(""), Cursor(), ParsedCommand("import", str(src)), ctx)
        new_buf = _imported(ctx)
        text = new_buf.text
        assert "    8 Fire // Ice\n" in text
        assert "    4 Bonecrusher Giant // Stomp\n" in text
        assert "    // Instants\n" in text and "    // Creatures\n" in text


def test_write_failure_is_reported(tmp_path: Path) -> None:
    ctx = EditorContext()
    _export(f"mtgo {tmp_path / 'missing-dir' / 'out.txt'}", ctx)
    assert ctx.error and "Write failed" in ctx.message

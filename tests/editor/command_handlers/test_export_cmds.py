"""Tests for :export and :import command handlers."""

from __future__ import annotations

import tempfile
from pathlib import Path

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.export_cmds import cmd_export, cmd_import
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _deck_text() -> str:
    return (
        "// Deck: Test Deck\n"
        "\n"
        "4 Lightning Bolt\n"
        "2 Counterspell\n"
        "\n"
        "SB: 1 Mystical Dispute\n"
    )


class TestExport:
    def test_export_mtgo(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="export", args="mtgo")

        result_buf, _ = cmd_export(buffer, cursor, cmd, ctx)
        assert "Exported mtgo" in ctx.message
        assert result_buf is buffer

    def test_export_arena(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="export", args="arena")

        cmd_export(buffer, cursor, cmd, ctx)
        assert "Exported arena" in ctx.message

    def test_export_moxfield(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="export", args="moxfield")

        cmd_export(buffer, cursor, cmd, ctx)
        assert "Exported moxfield" in ctx.message

    def test_export_archidekt(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="export", args="archidekt")

        cmd_export(buffer, cursor, cmd, ctx)
        assert "Exported archidekt" in ctx.message

    def test_export_to_file(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            out_path = f.name
        cmd = ParsedCommand(name="export", args=f"mtgo {out_path}")

        cmd_export(buffer, cursor, cmd, ctx)
        assert f"Exported mtgo to {out_path}" in ctx.message
        content = Path(out_path).read_text(encoding="utf-8")
        assert "Lightning Bolt" in content
        Path(out_path).unlink()

    def test_export_unknown_format(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="export", args="bogus")

        cmd_export(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "Unknown format" in ctx.message

    def test_export_no_format(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="export", args="")

        cmd_export(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "Usage" in ctx.message


class TestImport:
    def test_import_mtgo_file(self) -> None:
        mtgo_text = "4 Lightning Bolt\n2 Counterspell\n\nSideboard\n1 Mystical Dispute\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(mtgo_text)
            in_path = f.name

        buffer = Buffer.from_text("// Empty\n")
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="import", args=in_path)

        new_buf, _ = cmd_import(buffer, cursor, cmd, ctx)
        text = new_buf.to_text()
        assert "Lightning Bolt" in text
        assert "Counterspell" in text
        assert ctx.modified is True
        assert "Imported" in ctx.message
        Path(in_path).unlink()

    def test_import_file_not_found(self) -> None:
        buffer = Buffer.from_text("// Empty\n")
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="import", args="/nonexistent/file.txt")

        result_buf, _ = cmd_import(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "File not found" in ctx.message
        assert result_buf is buffer

    def test_import_no_file(self) -> None:
        buffer = Buffer.from_text("// Empty\n")
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="import", args="")

        cmd_import(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "Usage" in ctx.message

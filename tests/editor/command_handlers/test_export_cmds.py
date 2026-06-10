"""Tests for :export and :import command handlers."""

from __future__ import annotations

import tempfile
from pathlib import Path

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.export_cmds import cmd_clipboard, cmd_export, cmd_import
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


class TestClipboard:
    def test_clipboard_default_format_is_arena(self, capsys) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="clipboard", args="")

        cmd_clipboard(buffer, cursor, cmd, ctx)
        captured = capsys.readouterr()
        assert captured.out.startswith("\033]52;c;")
        assert "Copied arena to clipboard" in ctx.message

    def test_clipboard_explicit_format(self, capsys) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="clipboard", args="mtgo")

        cmd_clipboard(buffer, cursor, cmd, ctx)
        captured = capsys.readouterr()
        assert captured.out.startswith("\033]52;c;")
        assert "Copied mtgo to clipboard" in ctx.message

    def test_clipboard_unknown_format(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="clipboard", args="bogus")

        cmd_clipboard(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "Unknown format" in ctx.message


class _ResolvingRepo:
    """Stub CardRepository for import resolution tests."""

    def __init__(self, known: dict[str, object], fts: dict[str, list] | None = None) -> None:
        self._known = {n.lower(): c for n, c in known.items()}
        self._fts = fts or {}

    def get_by_name(self, name: str):  # noqa: ANN201
        return self._known.get(name.lower())

    def search(self, query: str, limit: int = 50) -> list:
        return self._fts.get(query, [])[:limit]


def _write_temp_deck(text: str) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(text)
        return Path(f.name)


class TestImportResolution:
    def test_import_all_resolved_has_clean_message(self) -> None:
        from vimtg.domain.card import Card, Prices, Rarity

        bolt = Card(
            scryfall_id="x", name="Lightning Bolt", mana_cost="{R}", cmc=1.0,
            type_line="Instant", oracle_text="", colors=(), color_identity=(),
            power=None, toughness=None, set_code="sta", rarity=Rarity.COMMON,
            prices=Prices(), legalities={}, image_uri=None, layout="normal",
            keywords=(),
        )
        path = _write_temp_deck("4 Lightning Bolt\n")
        buffer = Buffer.from_text("")
        ctx = EditorContext(card_repo=_ResolvingRepo({"Lightning Bolt": bolt}))
        cmd = ParsedCommand(name="import", args=str(path))

        cmd_import(buffer, Cursor(row=0), cmd, ctx)

        assert ctx.error is False
        assert "Imported 4 cards" in ctx.message
        assert "W100" not in ctx.message
        assert ctx.resolved_cards == {"Lightning Bolt": bolt}
        path.unlink()

    def test_import_unresolved_cards_warns_with_suggestion(self) -> None:
        from vimtg.domain.card import Card, Prices, Rarity

        bolt = Card(
            scryfall_id="x", name="Lightning Bolt", mana_cost="{R}", cmc=1.0,
            type_line="Instant", oracle_text="", colors=(), color_identity=(),
            power=None, toughness=None, set_code="sta", rarity=Rarity.COMMON,
            prices=Prices(), legalities={}, image_uri=None, layout="normal",
            keywords=(),
        )
        path = _write_temp_deck(
            "4 Lightening Bolt\n2 Fake Card One\n1 Fake Card Two\n"
        )
        repo = _ResolvingRepo({}, fts={"Lightening Bolt": [bolt]})
        buffer = Buffer.from_text("")
        ctx = EditorContext(card_repo=repo)
        cmd = ParsedCommand(name="import", args=str(path))

        result_buf, _ = cmd_import(buffer, Cursor(row=0), cmd, ctx)

        # Import is not blocked — buffer replaced, no error flag
        assert ctx.error is False
        assert "Lightening Bolt" in result_buf.to_text()
        assert "W100: 3 cards not found in database" in ctx.message
        assert "did you mean 'Lightning Bolt'" in ctx.message
        path.unlink()

    def test_import_without_repo_skips_resolution(self) -> None:
        path = _write_temp_deck("4 Lightning Bolt\n")
        buffer = Buffer.from_text("")
        ctx = EditorContext()
        cmd = ParsedCommand(name="import", args=str(path))

        cmd_import(buffer, Cursor(row=0), cmd, ctx)

        assert ctx.error is False
        assert "W100" not in ctx.message
        assert "Imported 4 cards" in ctx.message
        path.unlink()

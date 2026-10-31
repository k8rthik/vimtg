"""Tests for :export and :import command handlers."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.export_cmds import cmd_clipboard, cmd_export, cmd_import
from vimtg.editor.commands import EditorContext, NewBuffer, ParsedCommand
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
        # No file name: the export goes to the clipboard (the TUI copies)
        assert ctx.clipboard_text is not None and "Lightning Bolt" in ctx.clipboard_text
        assert ctx.clipboard_label.startswith("mtgo export (")
        assert result_buf is buffer

    def test_export_arena(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="export", args="arena")

        cmd_export(buffer, cursor, cmd, ctx)
        # No file name: the export goes to the clipboard (the TUI copies)
        assert ctx.clipboard_text is not None and "Lightning Bolt" in ctx.clipboard_text
        assert ctx.clipboard_label.startswith("arena export (")

    def test_export_moxfield(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="export", args="moxfield")

        cmd_export(buffer, cursor, cmd, ctx)
        # No file name: the export goes to the clipboard (the TUI copies)
        assert ctx.clipboard_text is not None and "Lightning Bolt" in ctx.clipboard_text
        assert ctx.clipboard_label.startswith("moxfield export (")

    def test_export_archidekt(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="export", args="archidekt")

        cmd_export(buffer, cursor, cmd, ctx)
        # No file name: the export goes to the clipboard (the TUI copies)
        assert ctx.clipboard_text is not None and "Lightning Bolt" in ctx.clipboard_text
        assert ctx.clipboard_label.startswith("archidekt export (")

    def test_export_to_file(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            out_path = f.name
        # The temp file exists, so overwriting it takes the bang
        cmd = ParsedCommand(name="export", args=f"mtgo {out_path}", bang=True)

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


def _imported(ctx: EditorContext) -> NewBuffer:
    """The new buffer an :import asked for (it never edits this one)."""
    assert ctx.new_buffer is not None and ctx.new_buffer.text is not None
    return ctx.new_buffer


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
        # The deck opens as a new unnamed buffer; this one is untouched
        assert new_buf is buffer
        imported = _imported(ctx)
        assert "Lightning Bolt" in imported.text
        assert "Counterspell" in imported.text
        assert "Imported" in imported.message
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

    def test_import_no_file_and_empty_clipboard(self, monkeypatch) -> None:  # noqa: ANN001
        from vimtg.editor.command_handlers import export_cmds

        monkeypatch.setattr(export_cmds, "read_clipboard", lambda: "")
        buffer = Buffer.from_text("// Empty\n")
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="import", args="")

        cmd_import(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert ":import <file|deck-url>" in ctx.message


class TestClipboard:
    """:clipboard renders the text; the TUI performs the copy (it owns
    the terminal) — the handler must never write to stdout itself."""

    def test_clipboard_default_format_is_arena(self, capsys) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="clipboard", args="")

        cmd_clipboard(buffer, cursor, cmd, ctx)
        assert capsys.readouterr().out == ""
        assert ctx.clipboard_text is not None
        assert "4 Lightning Bolt" in ctx.clipboard_text
        assert ctx.clipboard_label.startswith("arena (")
        assert ctx.error is False

    def test_clipboard_explicit_format(self, capsys) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="clipboard", args="mtgo")

        cmd_clipboard(buffer, cursor, cmd, ctx)
        assert capsys.readouterr().out == ""
        assert ctx.clipboard_label.startswith("mtgo (")
        assert ctx.clipboard_text is not None

    @pytest.mark.parametrize("fmt", ["vimtg", "arena", "mtgo", "moxfield", "guide"])
    def test_clipboard_text_is_the_export_text(self, fmt: str) -> None:
        text = (
            "// Deck: Burn\n\n// a note to self\n// Creature\n"
            "4 Goblin Guide  #fast  // keep\n\nSB:\n    2 Smash to Smithereens\n"
        )
        buffer = Buffer.from_text(text)
        exported, clipped = EditorContext(), EditorContext()
        cmd_export(buffer, Cursor(row=0), ParsedCommand(name="export", args=fmt), exported)
        cmd_clipboard(buffer, Cursor(row=0), ParsedCommand(name="clipboard", args=fmt), clipped)
        assert clipped.clipboard_text == exported.clipboard_text
        if fmt == "vimtg":
            assert clipped.clipboard_text == text

    def test_export_vimtg_writes_what_w_writes(self, tmp_path: Path) -> None:
        from vimtg.services.deck_service import scaffold_metadata

        raw = "// Deck: Burn\n\n4 Lightning Bolt\n"
        deck = tmp_path / "burn.deck"
        deck.write_text(raw, encoding="utf-8")
        buffer = Buffer.from_text(scaffold_metadata(raw)[0])
        assert "// Tags:" in buffer.to_text()
        ctx = EditorContext(file_path=deck)
        out = tmp_path / "copy.deck"
        cmd_export(buffer, Cursor(row=0), ParsedCommand(name="export", args=f"vimtg {out}"), ctx)
        assert not ctx.error, ctx.message
        assert out.read_text(encoding="utf-8") == raw

    def test_export_vimtg_of_a_new_deck_drops_empty_scaffold(self, tmp_path: Path) -> None:
        buffer = Buffer.from_text(
            "// Deck: Burn\n// Format:\n// Tags:\n\nDCK:\n    4 Lightning Bolt\n"
        )
        ctx = EditorContext()
        cmd_clipboard(buffer, Cursor(row=0), ParsedCommand(name="clipboard", args="vimtg"), ctx)
        assert ctx.clipboard_text == "// Deck: Burn\n\nDCK:\n    4 Lightning Bolt\n"

    def test_export_vimtg_keeps_empty_metadata_the_file_has(self, tmp_path: Path) -> None:
        raw = "// Deck: Burn\n// Format:\n// Tags:\n\n4 Lightning Bolt\n"
        deck = tmp_path / "burn.deck"
        deck.write_text(raw, encoding="utf-8")
        ctx = EditorContext(file_path=deck)
        cmd_clipboard(
            Buffer.from_text(raw), Cursor(row=0),
            ParsedCommand(name="clipboard", args="vimtg"), ctx,
        )
        assert ctx.clipboard_text == raw

    def test_clipboard_unknown_format(self) -> None:
        buffer = Buffer.from_text(_deck_text())
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="clipboard", args="bogus")

        cmd_clipboard(buffer, cursor, cmd, ctx)
        assert ctx.error is True
        assert "Unknown format" in ctx.message
        assert ctx.clipboard_text is None


class TestImportFromClipboard:
    def _run(self, monkeypatch, clip: str | None) -> tuple[Buffer, EditorContext]:  # noqa: ANN001
        from vimtg.editor.command_handlers import export_cmds

        monkeypatch.setattr(export_cmds, "read_clipboard", lambda: clip)
        buffer = Buffer.from_text(_deck_text())
        ctx = EditorContext()
        new_buf, _ = cmd_import(
            buffer, Cursor(row=0), ParsedCommand(name="import", args=""), ctx
        )
        return new_buf, ctx

    def test_bare_import_reads_clipboard_decklist(self, monkeypatch) -> None:  # noqa: ANN001
        _buf, ctx = self._run(
            monkeypatch, "Deck\n4 Ponder\n2 Brainstorm\nnot a card line\n"
        )
        imported = _imported(ctx)
        assert "4 Ponder" in imported.text and "2 Brainstorm" in imported.text
        assert "Lightning Bolt" not in imported.text  # a deck of its own
        assert "Imported 6 cards from clipboard" in imported.message
        assert "1 line(s) skipped" in imported.message

    def test_bare_import_clipboard_url_is_fetched(self, monkeypatch) -> None:  # noqa: ANN001
        url = "https://www.moxfield.com/decks/abc123"
        new_buf, ctx = self._run(monkeypatch, f"  {url}\n")
        assert ctx.import_url == url
        assert new_buf.to_text() == _deck_text()

    def test_unreadable_clipboard_fails_without_touching_deck(self, monkeypatch) -> None:  # noqa: ANN001
        new_buf, ctx = self._run(monkeypatch, None)
        assert ctx.error is True
        assert "Clipboard is empty or unreadable" in ctx.message
        assert new_buf.to_text() == _deck_text()

    def test_clipboard_without_cards_never_wipes_deck(self, monkeypatch) -> None:  # noqa: ANN001
        new_buf, ctx = self._run(monkeypatch, "hello there\nnothing here")
        assert ctx.error is True
        assert "No cards found in clipboard" in ctx.message
        assert new_buf.to_text() == _deck_text()
        assert ctx.modified is False


class _ResolvingRepo:
    """Stub CardRepository for import resolution tests."""

    def __init__(self, known: dict[str, object], fts: dict[str, list] | None = None) -> None:
        self._known = {n.lower(): c for n, c in known.items()}
        self._fts = fts or {}

    def get_by_name(self, name: str):  # noqa: ANN201
        return self._known.get(name.lower())

    def get_by_names(self, names: list[str]) -> dict[str, object]:
        return {n: c for n in names if (c := self.get_by_name(n)) is not None}

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
        imported = _imported(ctx)
        assert "Imported 4 cards" in imported.message
        assert "W100" not in imported.message
        assert "4 Lightning Bolt" in imported.text
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

        cmd_import(buffer, Cursor(row=0), cmd, ctx)

        # Import is not blocked — the deck opens, no error flag
        assert ctx.error is False
        imported = _imported(ctx)
        assert "Lightening Bolt" in imported.text
        assert "W100: 3 cards not found in database" in imported.message
        assert "did you mean 'Lightning Bolt'" in imported.message
        path.unlink()

    def test_import_without_repo_skips_resolution(self) -> None:
        path = _write_temp_deck("4 Lightning Bolt\n")
        buffer = Buffer.from_text("")
        ctx = EditorContext()
        cmd = ParsedCommand(name="import", args=str(path))

        cmd_import(buffer, Cursor(row=0), cmd, ctx)

        assert ctx.error is False
        assert "W100" not in _imported(ctx).message
        assert "Imported 4 cards" in _imported(ctx).message
        path.unlink()


class TestImportUrl:
    def test_url_arg_requests_fetch(self) -> None:
        buffer = Buffer.from_text("4 Lightning Bolt\n")
        ctx = EditorContext()
        cmd = ParsedCommand(
            name="import", args="https://moxfield.com/decks/abc123"
        )
        result_buf, _ = cmd_import(buffer, Cursor(), cmd, ctx)
        assert ctx.import_url == "https://moxfield.com/decks/abc123"
        assert not ctx.error
        assert result_buf is buffer  # fetch is async; buffer untouched here

    def test_file_path_still_reads_file(self) -> None:
        buffer = Buffer.from_text("4 Lightning Bolt\n")
        ctx = EditorContext()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "list.txt"
            path.write_text("4 Goblin Guide\n", encoding="utf-8")
            cmd = ParsedCommand(name="import", args=str(path))
            cmd_import(buffer, Cursor(), cmd, ctx)
        assert ctx.import_url == ""
        assert "Imported" in _imported(ctx).message


class TestImportRefusesUnsavedChanges:
    def test_modified_buffer_refuses_with_e37(self, tmp_path: Path) -> None:
        path = tmp_path / "list.txt"
        path.write_text("4 Goblin Guide\n", encoding="utf-8")
        ctx = EditorContext(modified=True)
        cmd_import(Buffer.from_text("4 Shock\n"), Cursor(), ParsedCommand("import", str(path)), ctx)
        assert ctx.error and ctx.message.startswith("E37:")
        assert ctx.new_buffer is None

    def test_bang_discards_them(self, tmp_path: Path) -> None:
        path = tmp_path / "list.txt"
        path.write_text("4 Goblin Guide\n", encoding="utf-8")
        ctx = EditorContext(modified=True)
        cmd = ParsedCommand("import", str(path), bang=True)
        cmd_import(Buffer.from_text("4 Shock\n"), Cursor(), cmd, ctx)
        assert not ctx.error
        assert "Goblin Guide" in _imported(ctx).text
        assert ctx.discard_requested


class TestExportMissing:
    """:export missing [file] — the shopping list against the collection."""

    def _collection(self, text: str):  # type: ignore[no-untyped-def]
        from vimtg.domain.collection import parse_collection_csv

        return parse_collection_csv(text, Path("manabox.csv"))

    def _ctx(self, collection_text: str | None) -> EditorContext:
        return EditorContext(
            collection=self._collection(collection_text) if collection_text else None
        )

    def test_copies_the_missing_list_to_the_clipboard(self) -> None:
        ctx = self._ctx("Count,Name\n3,Lightning Bolt\n1,Mystical Dispute\n")
        cmd_export(
            Buffer.from_text(_deck_text()), Cursor(),
            ParsedCommand(name="export", args="missing"), ctx,
        )
        assert ctx.error is False, ctx.message
        assert ctx.clipboard_text == "1 Lightning Bolt\n2 Counterspell\n"
        assert ctx.clipboard_label == "missing cards (2 lines)"

    def test_writes_the_list_to_a_file(self, tmp_path: Path) -> None:
        ctx = self._ctx("Count,Name\n4,Lightning Bolt\n2,Counterspell\n")
        out = tmp_path / "missing.txt"
        cmd_export(
            Buffer.from_text(_deck_text()), Cursor(),
            ParsedCommand(name="export", args=f"missing {out}"), ctx,
        )
        assert ctx.error is False, ctx.message
        assert out.read_text(encoding="utf-8") == "1 Mystical Dispute\n"
        assert ctx.message == f"Exported missing cards to {out}"

    def test_fails_without_a_collection(self) -> None:
        ctx = self._ctx(None)
        cmd_export(
            Buffer.from_text(_deck_text()), Cursor(),
            ParsedCommand(name="export", args="missing"), ctx,
        )
        assert ctx.error is True
        assert ctx.message == "E: No collection loaded (:collection path.csv)"
        assert ctx.clipboard_text is None

    def test_reports_a_complete_deck_instead_of_copying_nothing(self) -> None:
        ctx = self._ctx("Count,Name\n4,Lightning Bolt\n2,Counterspell\n1,Mystical Dispute\n")
        cmd_export(
            Buffer.from_text(_deck_text()), Cursor(),
            ParsedCommand(name="export", args="missing"), ctx,
        )
        assert ctx.error is False
        assert ctx.clipboard_text is None
        assert ctx.message == "Nothing missing: the collection covers this deck"

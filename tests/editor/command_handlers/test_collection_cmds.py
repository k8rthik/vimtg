""":collection — load, report, and clear the owned-cards collection."""

from __future__ import annotations

from pathlib import Path

import pytest

from vimtg.config.settings import Settings
from vimtg.domain.collection import parse_collection_csv
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers import register_all_commands
from vimtg.editor.commands import CommandRegistry, EditorContext, parse_command
from vimtg.editor.cursor import Cursor


@pytest.fixture
def registry() -> CommandRegistry:
    reg = CommandRegistry()
    register_all_commands(reg)
    return reg


def _run(registry: CommandRegistry, line: str, ctx: EditorContext) -> EditorContext:
    buffer = Buffer.from_text("4 Lightning Bolt\n")
    cmd = parse_command(line, 0, 1)
    assert cmd is not None
    registry.execute(cmd, buffer, Cursor(), ctx)
    return ctx


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    path = tmp_path / "manabox.csv"
    path.write_text("Quantity,Name\n2,Lightning Bolt\n1,Goblin Guide\n", encoding="utf-8")
    return path


def test_collection_path_loads_and_saves_the_setting(
    registry: CommandRegistry, csv_path: Path
) -> None:
    ctx = _run(registry, f"collection {csv_path}", EditorContext(settings=Settings()))
    assert ctx.error is False
    assert ctx.message == "Collection: 3 cards (2 unique) from manabox.csv"
    assert ctx.settings_changed is True
    assert ctx.settings.collection == str(csv_path)
    assert ctx.collection_set is True
    assert ctx.collection is not None
    assert ctx.collection.owned_count("Lightning Bolt") == 2


def test_collection_path_expands_tilde(
    registry: CommandRegistry, csv_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(csv_path.parent))
    ctx = _run(registry, "collection ~/manabox.csv", EditorContext(settings=Settings()))
    assert ctx.error is False, ctx.message
    assert ctx.settings.collection == str(csv_path)


def test_bare_collection_reports_none_loaded(registry: CommandRegistry) -> None:
    ctx = _run(registry, "collection", EditorContext(settings=Settings()))
    assert ctx.message == "No collection loaded (:collection path.csv)"
    assert ctx.error is False
    assert ctx.settings_changed is False


def test_bare_collection_reports_the_loaded_one(
    registry: CommandRegistry, csv_path: Path
) -> None:
    loaded = parse_collection_csv(csv_path.read_text(encoding="utf-8"), csv_path)
    ctx = _run(
        registry, "collection",
        EditorContext(settings=Settings(collection=str(csv_path)), collection=loaded),
    )
    assert ctx.message == "Collection: 3 cards (2 unique) from manabox.csv"
    assert ctx.collection_set is False


def test_bang_clears_the_collection_and_the_setting(
    registry: CommandRegistry, csv_path: Path
) -> None:
    loaded = parse_collection_csv(csv_path.read_text(encoding="utf-8"), csv_path)
    ctx = _run(
        registry, "collection!",
        EditorContext(settings=Settings(collection=str(csv_path)), collection=loaded),
    )
    assert ctx.message == "Collection cleared"
    assert ctx.settings_changed is True
    assert ctx.settings.collection == ""
    assert ctx.collection_set is True
    assert ctx.collection is None


def test_missing_file_fails_and_keeps_the_old_collection(
    registry: CommandRegistry, csv_path: Path, tmp_path: Path
) -> None:
    loaded = parse_collection_csv(csv_path.read_text(encoding="utf-8"), csv_path)
    ctx = _run(
        registry, f"collection {tmp_path / 'nope.csv'}",
        EditorContext(settings=Settings(collection=str(csv_path)), collection=loaded),
    )
    assert ctx.error is True
    assert "not found" in ctx.message
    assert ctx.settings_changed is False
    assert ctx.collection_set is False


def test_unrecognisable_csv_names_its_headers(
    registry: CommandRegistry, tmp_path: Path
) -> None:
    path = tmp_path / "odd.csv"
    path.write_text("Card,Amount\nLightning Bolt,4\n", encoding="utf-8")
    ctx = _run(registry, f"collection {path}", EditorContext(settings=Settings()))
    assert ctx.error is True
    assert "Card, Amount" in ctx.message

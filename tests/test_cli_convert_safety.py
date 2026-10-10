"""`vimtg convert`: -o never overwrites by accident, vimtg -> vimtg is
lossless, and the synced card database supplies official names."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from vimtg.cli import main
from vimtg.config.paths import db_path
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card

_DECK = (
    "// Deck: Burn\n"
    "// Format: modern\n"
    "\n"
    "// Creatures\n"
    "4 Goblin Guide  @aggro\n"
    "\n"
    "// Spells\n"
    "4 Stomp\n"
    "4 Fire/Ice\n"
    "\n"
    "SB:\n"
    "    2 Smash to Smithereens\n"
)


@pytest.fixture
def deck_file(tmp_path: Path) -> Path:
    path = tmp_path / "b.deck"
    path.write_text(_DECK, encoding="utf-8")
    return path


@pytest.fixture
def synced_db(real_shape_cards: list[dict[str, Any]]) -> None:
    """The real-shape cards in the CLI's (isolated) card database."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(path)
    db.initialize()
    CardRepository(db).replace_all([Card.from_scryfall(d) for d in real_shape_cards])
    db.close()


def test_refuses_to_overwrite_existing_output(deck_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "list.txt"
    out.write_text("keep\n", encoding="utf-8")
    result = CliRunner().invoke(
        main, ["convert", str(deck_file), "--to", "mtgo", "-o", str(out)]
    )
    assert result.exit_code != 0
    assert "--force" in result.output
    assert out.read_text(encoding="utf-8") == "keep\n"


def test_force_overwrites_existing_output(deck_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "list.txt"
    out.write_text("keep\n", encoding="utf-8")
    result = CliRunner().invoke(
        main, ["convert", str(deck_file), "--to", "mtgo", "-o", str(out), "--force"]
    )
    assert result.exit_code == 0, result.output
    assert "4 Goblin Guide" in out.read_text(encoding="utf-8")


@pytest.mark.parametrize("extra", [[], ["--force"]])
def test_never_overwrites_the_input(deck_file: Path, extra: list[str]) -> None:
    result = CliRunner().invoke(
        main, ["convert", str(deck_file), "--to", "mtgo", "-o", str(deck_file), *extra]
    )
    assert result.exit_code != 0
    assert "input file" in result.output
    assert deck_file.read_text(encoding="utf-8") == _DECK


def test_tilde_output_is_expanded(
    deck_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows ~
    result = CliRunner().invoke(
        main, ["convert", str(deck_file), "--to", "arena", "-o", "~/arena.txt"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "arena.txt").is_file()


def test_vimtg_to_vimtg_is_lossless(deck_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "copy.deck"
    result = CliRunner().invoke(
        main, ["convert", str(deck_file), "--to", "vimtg", "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8") == _DECK


def test_foreign_to_vimtg_gets_structured_layout(tmp_path: Path) -> None:
    src = tmp_path / "burn.txt"
    src.write_text("4 Lightning Bolt\n20 Mountain\n\n2 Duress\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["convert", str(src), "--to", "vimtg"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("// Deck: burn\n// Format:\n\nDCK:\n")
    assert "SB:\n    2 Duress\n" in result.output


@pytest.mark.usefixtures("synced_db")
def test_uses_card_database_for_official_names(deck_file: Path) -> None:
    result = CliRunner().invoke(main, ["convert", str(deck_file), "--to", "mtgo"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert "4 Bonecrusher Giant" in lines
    assert "4 Fire // Ice" in lines
    assert "4 Stomp" not in lines and "4 Fire/Ice" not in lines


def test_without_card_database_still_converts(deck_file: Path) -> None:
    result = CliRunner().invoke(main, ["convert", str(deck_file), "--to", "mtgo"])
    assert result.exit_code == 0, result.output
    assert "4 Stomp" in result.output.splitlines()


def test_empty_card_database_is_ignored(deck_file: Path) -> None:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(path)
    db.initialize()
    db.close()
    result = CliRunner().invoke(main, ["convert", str(deck_file), "--to", "mtgo"])
    assert result.exit_code == 0, result.output
    assert "4 Stomp" in result.output.splitlines()


def test_unreadable_card_database_is_ignored(deck_file: Path) -> None:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this is not a sqlite database" * 100)
    result = CliRunner().invoke(main, ["convert", str(deck_file), "--to", "mtgo"])
    assert result.exit_code == 0, result.output
    assert "4 Stomp" in result.output.splitlines()

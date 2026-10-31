"""`vimtg convert` runs the destination's checks: errors stop it with
exit 1 unless --force, warnings go to stderr, stdout is only the export."""

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

_DECK = "// Deck: Burn\n\n4 Goblin Guide\n4 Lightning Bolt\n\nSB: 2 Lightning Bolt\n"


def _card(name: str, timeless: str) -> Card:
    data: dict[str, Any] = {
        "id": name,
        "name": name,
        "type_line": "Instant",
        "legalities": {"modern": "legal", "timeless": timeless},
        "prices": {"tix": "0.10"},
    }
    return Card.from_scryfall(data)


@pytest.fixture
def deck_file(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(_DECK, encoding="utf-8")
    return path


@pytest.fixture
def synced_db() -> None:
    """A card database where Goblin Guide is not on Arena."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(path)
    db.initialize()
    cards = [_card("Goblin Guide", "not_legal"), _card("Lightning Bolt", "legal")]
    CardRepository(db).replace_all(cards)
    db.close()


def _convert(*args: str) -> Any:
    return CliRunner().invoke(main, ["convert", *args])


@pytest.mark.usefixtures("synced_db")
def test_an_error_exits_1_and_writes_nothing_to_stdout(deck_file: Path) -> None:
    result = _convert(str(deck_file), "--to", "arena")
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Not on MTG Arena" in result.stderr and "Goblin Guide" in result.stderr
    assert "--force" in result.stderr


@pytest.mark.usefixtures("synced_db")
def test_an_error_leaves_the_output_file_unwritten(deck_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "arena.txt"
    result = _convert(str(deck_file), "--to", "mtga", "-o", str(out))
    assert result.exit_code == 1
    assert not out.exists()


@pytest.mark.usefixtures("synced_db")
def test_force_writes_despite_an_error(deck_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "arena.txt"
    result = _convert(str(deck_file), "--to", "arena", "-o", str(out), "--force")
    assert result.exit_code == 0, result.output
    assert "4 Goblin Guide" in out.read_text(encoding="utf-8").splitlines()
    assert "Goblin Guide" in result.stderr


@pytest.mark.usefixtures("synced_db")
def test_a_clean_export_says_nothing_on_stderr(deck_file: Path) -> None:
    result = _convert(str(deck_file), "--to", "moxfield")
    assert result.exit_code == 0
    assert result.stderr == ""


def test_warnings_go_to_stderr_and_exit_0(deck_file: Path) -> None:
    result = _convert(str(deck_file), "--to", "mtgo")  # no card database
    assert result.exit_code == 0
    assert result.stdout == "4 Goblin Guide\n4 Lightning Bolt\n\nSideboard\n2 Lightning Bolt\n\n"
    assert "warning:" in result.stderr and "limited" in result.stderr


def test_dash_output_is_stdout_with_only_the_export(
    deck_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = _convert(str(deck_file), "--to", "mtgo", "-o", "-")
    assert result.exit_code == 0
    assert result.stdout == _convert(str(deck_file), "--to", "mtgo").stdout
    assert not Path("-").exists()


def test_mpc_reports_its_card_count(deck_file: Path, tmp_path: Path) -> None:
    to_stdout = _convert(str(deck_file), "--to", "mpc")
    assert to_stdout.stdout == "4 Goblin Guide\n6 Lightning Bolt\n\n"
    assert "10 cards" in to_stdout.stderr
    out = tmp_path / "mpc.txt"
    to_file = _convert(str(deck_file), "--to", "mpc", "-o", str(out))
    assert to_file.stdout == f"Converted to {out} (10 cards)\n"


def test_mpc_refuses_an_at_sign(tmp_path: Path) -> None:
    deck = tmp_path / "at.deck"
    deck.write_text("1 Foo@Bar\n", encoding="utf-8")
    result = _convert(str(deck), "--to", "mpc")
    assert result.exit_code == 1
    assert "Foo@Bar" in result.stderr

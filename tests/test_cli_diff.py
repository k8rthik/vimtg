"""`vimtg diff a.deck b.deck`: card-level changes, diff(1) exit codes."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner

from vimtg import cli
from vimtg.cli import main
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card

_OLD = (
    "// Deck: Burn\n"
    "// Format: modern\n"
    "4 Lightning Bolt\n"
    "3 Lava Spike\n"
    "1 Goblin Guide\n"
    "52 Mountain\n"
    "SB: 2 Rest in Peace\n"
)
_NEW = (
    "// Deck: Burn\n"
    "// Format: modern\n"
    "4 Lightning Bolt\n"
    "4 Lava Spike\n"
    "2 Eidolon of the Great Revel\n"
    "50 Mountain\n"
    "SB: 2 Rest in Peace\n"
    "SB: 1 Goblin Guide\n"
)


@pytest.fixture
def decks(tmp_path: Path) -> tuple[Path, Path]:
    old = tmp_path / "old.deck"
    new = tmp_path / "new.deck"
    old.write_text(_OLD, encoding="utf-8")
    new.write_text(_NEW, encoding="utf-8")
    return old, new


@pytest.fixture
def no_card_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)


@pytest.fixture
def sample_repo(
    db_factory: Callable[..., Database],
    scryfall_sample_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> CardRepository:
    repo = CardRepository(db_factory())
    raw = json.loads(scryfall_sample_path.read_text(encoding="utf-8"))
    repo.replace_all([Card.from_scryfall(c) for c in raw])
    monkeypatch.setattr(cli, "_try_card_repo", lambda: repo)
    return repo


@pytest.mark.usefixtures("no_card_db")
def test_diff_prints_changes_by_zone_and_exits_1(decks: tuple[Path, Path]) -> None:
    old, new = decks
    result = CliRunner().invoke(main, ["diff", str(old), str(new)])
    assert result.exit_code == 1
    assert result.stdout == (
        "Mainboard:\n"
        "  + 2 Eidolon of the Great Revel\n"
        "  ~ Lava Spike  3 → 4\n"
        "  ~ Mountain  52 → 50\n"
        "Sideboard:\n"
        "  ⇄ Goblin Guide  main → sideboard\n"
    )


@pytest.mark.usefixtures("no_card_db")
def test_diff_of_identical_decks_prints_nothing_and_exits_0(
    decks: tuple[Path, Path],
) -> None:
    old, _new = decks
    result = CliRunner().invoke(main, ["diff", str(old), str(old)])
    assert result.exit_code == 0, result.output
    assert result.stdout == ""


@pytest.mark.usefixtures("no_card_db")
def test_diff_ignores_lines_that_are_not_cards(tmp_path: Path) -> None:
    old = tmp_path / "a.deck"
    new = tmp_path / "b.deck"
    old.write_text("// Deck: A\n4 Lightning Bolt\n", encoding="utf-8")
    new.write_text("// Deck: B\n// sideboard ideas below\n4 Lightning Bolt\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["diff", str(old), str(new)])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "same cards" in result.stderr


@pytest.mark.usefixtures("no_card_db")
def test_diff_removed_card(tmp_path: Path) -> None:
    old = tmp_path / "a.deck"
    new = tmp_path / "b.deck"
    old.write_text("4 Lightning Bolt\n1 Skullcrack\n", encoding="utf-8")
    new.write_text("4 Lightning Bolt\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["diff", str(old), str(new)])
    assert result.exit_code == 1
    assert result.stdout == "Mainboard:\n  - 1 Skullcrack\n"


def test_diff_adds_a_stats_line_with_card_data(
    decks: tuple[Path, Path], sample_repo: CardRepository
) -> None:
    old, new = decks
    result = CliRunner().invoke(main, ["diff", str(old), str(new)])
    assert result.exit_code == 1
    # Old: 4 Bolt 1.50, 3 Lava Spike 0.50, 1 Goblin Guide 3.50 (main) = 11.00
    #      and 2 Rest in Peace 4.00 (sideboard, not counted in price)
    # New: 4 Bolt, 4 Lava Spike, 2 Eidolon 2.00 = 6 + 2 + 4 = 12.00
    assert result.stdout.splitlines()[-1] == (
        "Stats: 62 → 63 cards | Avg CMC 1.00 → 1.20 | $11.00 → $12.00 (usd)"
    )


@pytest.mark.usefixtures("no_card_db")
def test_diff_json(decks: tuple[Path, Path]) -> None:
    old, new = decks
    result = CliRunner().invoke(main, ["diff", "--json", str(old), str(new)])
    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "schema": "vimtg.diff/1",
        "old": str(old),
        "new": str(new),
        "identical": False,
        "changes": [
            {"name": "Eidolon of the Great Revel", "change": "added",
             "old": None, "new": {"zone": "main", "quantity": 2}},
            {"name": "Lava Spike", "change": "quantity_changed",
             "old": {"zone": "main", "quantity": 3}, "new": {"zone": "main", "quantity": 4}},
            {"name": "Mountain", "change": "quantity_changed",
             "old": {"zone": "main", "quantity": 52}, "new": {"zone": "main", "quantity": 50}},
            {"name": "Goblin Guide", "change": "section_moved",
             "old": {"zone": "main", "quantity": 1},
             "new": {"zone": "sideboard", "quantity": 1}},
        ],
        "stats": None,
    }


def test_diff_json_stats(decks: tuple[Path, Path], sample_repo: CardRepository) -> None:
    old, new = decks
    result = CliRunner().invoke(main, ["diff", "--json", str(old), str(new)])
    stats = json.loads(result.stdout)["stats"]
    assert stats["old"] == {"total_cards": 62, "average_cmc": 1.0, "price": 11.0}
    assert stats["new"] == {"total_cards": 63, "average_cmc": 1.2, "price": 12.0}
    assert stats["price_source"] == "usd"
    # Lava Spike +1 and Goblin Guide -1 at mana value 1, Eidolon +2 at 2
    assert stats["curve_delta"] == [0, 0, 2, 0, 0, 0, 0, 0]


@pytest.mark.usefixtures("no_card_db")
def test_diff_json_identical(decks: tuple[Path, Path]) -> None:
    old, _new = decks
    result = CliRunner().invoke(main, ["diff", "--json", str(old), str(old)])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert (doc["identical"], doc["changes"]) == (True, [])


@pytest.mark.usefixtures("no_card_db")
def test_diff_reads_one_side_from_stdin(decks: tuple[Path, Path]) -> None:
    old, new = decks
    result = CliRunner().invoke(main, ["diff", "-", str(new)], input=_OLD)
    assert result.exit_code == 1
    assert "~ Lava Spike  3 → 4" in result.stdout


@pytest.mark.usefixtures("no_card_db")
def test_diff_missing_file_exits_2(decks: tuple[Path, Path], tmp_path: Path) -> None:
    old, _new = decks
    result = CliRunner().invoke(main, ["diff", str(old), str(tmp_path / "nope.deck")])
    assert result.exit_code == 2
    assert result.stdout == ""


@pytest.mark.usefixtures("no_card_db")
def test_diff_unreadable_file_exits_2(decks: tuple[Path, Path], tmp_path: Path) -> None:
    old, _new = decks
    binary = tmp_path / "latin1.deck"
    binary.write_bytes("4 J\xf6tun Grunt\n".encode("latin-1"))
    result = CliRunner().invoke(main, ["diff", str(old), str(binary)])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "not UTF-8" in result.stderr


@pytest.mark.usefixtures("no_card_db")
def test_diff_both_sides_from_stdin_is_a_usage_error() -> None:
    result = CliRunner().invoke(main, ["diff", "-", "-"], input=_OLD)
    assert result.exit_code == 2
    assert result.stdout == ""


@pytest.mark.usefixtures("no_card_db")
def test_diff_needs_two_files(decks: tuple[Path, Path]) -> None:
    old, _new = decks
    result = CliRunner().invoke(main, ["diff", str(old)])
    assert result.exit_code == 2

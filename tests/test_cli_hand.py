"""`vimtg hand FILE [--seed N] [--draws N] [--plan NAME]`."""

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

FIXTURES_DIR = Path(__file__).parent / "fixtures"

DECK = """\
// Deck: Burn
// Format: modern

DCK:
4 Goblin Guide
4 Sacred Foundry
16 Mountain
36 Lava Spike

SB: 4 Skullcrack

VS: Tron
    -4 Goblin Guide
    +4 Skullcrack
"""


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def deck(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(DECK, encoding="utf-8")
    return path


@pytest.fixture
def loaded_repo(db_factory: Callable[..., Database]) -> CardRepository:
    repo = CardRepository(db_factory())
    with open(FIXTURES_DIR / "scryfall_sample.json", encoding="utf-8") as f:
        repo.bulk_insert([Card.from_scryfall(d) for d in json.load(f)])
    return repo


def _hand_lines(output: str) -> list[str]:
    lines = output.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Opening hand"))
    return [line.strip() for line in lines[start + 1 : start + 8]]


def test_prints_seven_cards_and_odds(runner: CliRunner, deck: Path) -> None:
    result = runner.invoke(main, ["hand", str(deck), "--seed", "42"])
    assert result.exit_code == 0, result.output
    assert "seed=42" in result.output
    hand = _hand_lines(result.output)
    assert len(hand) == 7
    assert set(hand) <= {"Goblin Guide", "Sacred Foundry", "Mountain", "Lava Spike"}
    assert "P(>=1 land in 7)" in result.output
    assert "P(>=2 lands in 7)" in result.output


def test_seed_is_deterministic(runner: CliRunner, deck: Path) -> None:
    a = runner.invoke(main, ["hand", str(deck), "--seed", "5", "--draws", "3"])
    b = runner.invoke(main, ["hand", str(deck), "--seed", "5", "--draws", "3"])
    assert a.exit_code == 0 and a.output == b.output
    assert "Draws:" in a.output and "  3. " in a.output


def test_no_database_counts_basics_only(runner: CliRunner, deck: Path) -> None:
    result = runner.invoke(main, ["hand", str(deck), "--seed", "1"])
    assert "Lands: 16 of 60" in result.output
    assert "no card database" in result.output  # stderr is mixed in by CliRunner


def test_database_resolves_nonbasic_lands(
    runner: CliRunner,
    deck: Path,
    loaded_repo: CardRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: loaded_repo)
    result = runner.invoke(main, ["hand", str(deck), "--seed", "1"])
    assert result.exit_code == 0, result.output
    assert "Lands: 20 of 60" in result.output
    assert "no card database" not in result.output


def test_plan_option(runner: CliRunner, deck: Path) -> None:
    result = runner.invoke(main, ["hand", str(deck), "--seed", "1", "--plan", "tron"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[1] == "Plan: vs Tron"
    assert "Goblin Guide" not in result.output


def test_unknown_plan_errors(runner: CliRunner, deck: Path) -> None:
    result = runner.invoke(main, ["hand", str(deck), "--plan", "elves"])
    assert result.exit_code != 0
    assert "No sideboard plan named 'elves'" in result.output


def test_commander_zone(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "cmd.deck"
    path.write_text(
        "// Format: commander\nCMD: 1 Atraxa, Praetors' Voice\nDCK:\n99 Forest\n",
        encoding="utf-8",
    )
    result = runner.invoke(main, ["hand", str(path), "--seed", "1"])
    assert result.exit_code == 0, result.output
    assert "Command zone: Atraxa, Praetors' Voice" in result.output
    assert "Atraxa" not in "\n".join(_hand_lines(result.output))
    assert "Lands: 99 of 99" in result.output


def test_empty_main_deck_errors(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "side.deck"
    path.write_text("SB: 4 Duress\n", encoding="utf-8")
    result = runner.invoke(main, ["hand", str(path)])
    assert result.exit_code != 0
    assert "No cards in the main deck" in result.output


def test_draws_capped_by_library(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "small.deck"
    path.write_text("DCK:\n9 Mountain\n", encoding="utf-8")
    result = runner.invoke(main, ["hand", str(path), "--draws", "10"])
    assert result.exit_code == 0, result.output
    assert "  2. Mountain" in result.output and "  3. " not in result.output


def test_negative_draws_rejected(runner: CliRunner, deck: Path) -> None:
    result = runner.invoke(main, ["hand", str(deck), "--draws", "-1"])
    assert result.exit_code == 2

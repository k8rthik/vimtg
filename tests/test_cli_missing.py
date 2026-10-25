"""`vimtg missing`: the shopping list against a collection CSV, and the
cost to finish the deck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner

from vimtg import cli
from vimtg.cli import main
from vimtg.config.paths import config_dir
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card

_DECK = (
    "// Deck: Burn\n"
    "4 Lightning Bolt\n"
    "2 Lava Spike\n"
    "20 Mountain\n"
    "SB: 3 Rest in Peace\n"
)


@pytest.fixture
def deck_file(tmp_path: Path) -> Path:
    path = tmp_path / "burn.deck"
    path.write_text(_DECK, encoding="utf-8")
    return path


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    path = tmp_path / "manabox.csv"
    path.write_text("Name,Quantity\nLightning Bolt,3\nMountain,20\n", encoding="utf-8")
    return path


@pytest.fixture
def sample_repo(
    db_factory: Callable[..., Database], scryfall_sample_path: Path
) -> CardRepository:
    import json

    repo = CardRepository(db_factory())
    raw = json.loads(scryfall_sample_path.read_text(encoding="utf-8"))
    repo.replace_all([Card.from_scryfall(c) for c in raw])
    return repo


def test_prints_the_list_and_the_total(
    deck_file: Path, csv_file: Path, sample_repo: CardRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: sample_repo)
    result = CliRunner().invoke(
        main, ["missing", str(deck_file), "--collection", str(csv_file)]
    )
    assert result.exit_code == 0, result.output + result.stderr
    assert result.stdout == "1 Lightning Bolt\n2 Lava Spike\n\n3 Rest in Peace\n"
    # 1 Bolt at 1.50, 2 Lava Spike at 0.50, 3 Rest in Peace at 4.00
    assert result.stderr == "Total to complete: $14.50 (usd)\n"


def test_uses_the_configured_collection(
    deck_file: Path, csv_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    config_dir().mkdir(parents=True, exist_ok=True)
    (config_dir() / "config.toml").write_text(
        f'[editor]\ncollection = "{csv_file}"\n', encoding="utf-8"
    )
    result = CliRunner().invoke(main, ["missing", str(deck_file)])
    assert result.exit_code == 0, result.output + result.stderr
    assert result.stdout.splitlines()[0] == "1 Lightning Bolt"
    assert result.stderr == "Total to complete: unknown (no card database; run vimtg sync)\n"


def test_fails_without_a_collection(deck_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    result = CliRunner().invoke(main, ["missing", str(deck_file)])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == (
        "No collection configured: pass --collection file.csv, or load one "
        "with :collection in the editor\n"
    )


def test_fails_on_an_unusable_csv(
    deck_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    odd = tmp_path / "odd.csv"
    odd.write_text("Card,Amount\nLightning Bolt,4\n", encoding="utf-8")
    result = CliRunner().invoke(
        main, ["missing", str(deck_file), "--collection", str(odd)]
    )
    assert result.exit_code == 1
    assert "Card, Amount" in result.stderr


def test_complete_deck_prints_nothing_but_says_so(
    deck_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    full = tmp_path / "full.csv"
    full.write_text(
        "Count,Name\n4,Lightning Bolt\n2,Lava Spike\n20,Mountain\n3,Rest in Peace\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        main, ["missing", str(deck_file), "--collection", str(full)]
    )
    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr == "Nothing missing: the collection covers burn.deck\n"

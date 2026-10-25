"""`vimtg validate` reports the Commander bracket estimate as info only."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from vimtg import cli
from vimtg.cli import main
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def repo(
    db_factory: Callable[..., Database], real_shape_cards: list[dict[str, Any]]
) -> CardRepository:
    extra = json.loads(
        (FIXTURES / "scryfall_mana_analytics.json").read_text(encoding="utf-8")
    )
    r = CardRepository(db_factory())
    r.replace_all([Card.from_scryfall(d) for d in real_shape_cards + extra])
    return r


def _commander_deck(tmp_path: Path, game_changers: list[str]) -> Path:
    body = "".join(f"1 {n}\n" for n in game_changers)
    filler = 99 - len(game_changers)
    deck = tmp_path / "aurelia.deck"
    deck.write_text(
        "// Format: commander\nCMD: 1 Aurelia, the Warleader\n"
        f"{body}{filler} Mountain\n",
        encoding="utf-8",
    )
    return deck


def test_bracket_info_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: CardRepository
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: repo)
    deck = _commander_deck(
        tmp_path,
        ["Smothering Tithe", "Enlightened Tutor", "Gamble", "Jeska's Will"],
    )
    result = CliRunner().invoke(main, ["validate", str(deck)])
    assert result.exit_code == 0, result.output
    assert "aurelia.deck: ok (commander)" in result.output
    assert (
        "info: 4 Game Changers (Smothering Tithe, Enlightened Tutor, Gamble, "
        "Jeska's Will); estimated Commander bracket 4+" in result.output
    )


def test_bracket_info_never_fails_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: CardRepository
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: repo)
    deck = _commander_deck(tmp_path, ["Smothering Tithe"])
    result = CliRunner().invoke(main, ["validate", "--strict", str(deck)])
    assert result.exit_code == 0, result.output
    assert "estimated Commander bracket 3" in result.output
    assert "warning" not in result.output


def test_no_bracket_line_for_other_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: CardRepository
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: repo)
    deck = tmp_path / "burn.deck"
    deck.write_text("// Format: modern\n4 Gamble\n56 Mountain\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["validate", str(deck)])
    assert "bracket" not in result.output


def test_no_bracket_line_without_card_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    deck = _commander_deck(tmp_path, ["Smothering Tithe"])
    result = CliRunner().invoke(main, ["validate", str(deck)])
    assert "bracket" not in result.output


def test_bracket_in_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: CardRepository
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: repo)
    deck = _commander_deck(tmp_path, ["Smothering Tithe", "Gamble"])
    result = CliRunner().invoke(main, ["validate", "--json", str(deck)])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["ok"] is True
    assert doc["bracket"].startswith("2 Game Changers (Smothering Tithe, Gamble)")

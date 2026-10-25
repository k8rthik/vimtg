"""`--json`: one JSON document on stdout, notes still on stderr, exit
codes unchanged."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from vimtg import cli
from vimtg.cli import main
from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card


@pytest.fixture
def sample_repo(
    db_factory: Callable[..., Database], scryfall_sample_path: Path
) -> CardRepository:
    repo = CardRepository(db_factory())
    repo.replace_all(
        [Card.from_scryfall(c) for c in json.loads(scryfall_sample_path.read_text())]
    )
    return repo


def _deck(tmp_path: Path, text: str, name: str = "burn.deck") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _doc(result: Result) -> Any:
    return json.loads(result.stdout)


# --- validate ---


def test_validate_json_ok_without_card_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    deck = _deck(tmp_path, "// Format: modern\n4 Lightning Bolt\n56 Mountain\n")
    result = CliRunner().invoke(main, ["validate", "--json", str(deck)])
    assert result.exit_code == 0, result.output
    assert _doc(result) == {
        "schema": "vimtg.validation/1",
        "file": str(deck),
        "format": "modern",
        "ok": True,
        "legality_checked": False,
        "problems": [],
        "bracket": None,
    }
    assert "legality checks skipped" in result.stderr


def test_validate_json_reports_errors_and_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_repo: CardRepository
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: sample_repo)
    deck = _deck(tmp_path, "// Format: modern\n5 Lightning Bolt\n55 Mountain\n")
    result = CliRunner().invoke(main, ["validate", "--json", str(deck)])
    assert result.exit_code == 1
    doc = _doc(result)
    assert doc["ok"] is False
    assert doc["legality_checked"] is True
    assert doc["format"] == "modern"
    errors = [p for p in doc["problems"] if p["level"] == "error"]
    assert len(errors) == 1
    assert errors[0]["line"] == 2
    assert "Lightning Bolt: 5 copies" in errors[0]["message"]


def test_validate_json_warnings_fail_only_with_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_repo: CardRepository
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: sample_repo)
    deck = _deck(
        tmp_path,
        "// Format: modern\n4 Lightning Bolt\n4 Not A Real Card\n52 Mountain\n",
    )
    loose = CliRunner().invoke(main, ["validate", "--json", str(deck)])
    assert loose.exit_code == 0, loose.output
    assert _doc(loose)["ok"] is True
    warning = _doc(loose)["problems"][0]
    assert (warning["line"], warning["level"]) == (3, "warning")
    assert "Not A Real Card" in warning["message"]

    strict = CliRunner().invoke(main, ["validate", "--json", "--strict", str(deck)])
    assert strict.exit_code == 1
    assert _doc(strict)["ok"] is False


def test_validate_json_strict_without_card_data_prints_no_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    deck = _deck(tmp_path, "4 Lightning Bolt\n")
    result = CliRunner().invoke(main, ["validate", "--json", "--strict", str(deck)])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "--strict needs a card database" in result.stderr

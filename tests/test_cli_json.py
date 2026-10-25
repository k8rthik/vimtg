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
    raw = json.loads(scryfall_sample_path.read_text(encoding="utf-8"))
    repo.replace_all([Card.from_scryfall(c) for c in raw])
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


# --- info ---

_ZONED_DECK = (
    "// Deck: Lurrus Burn\n"
    "CMP: 1 Lurrus of the Dream-Den\n"
    "4 Lightning Bolt\n"
    "52 Mountain\n"
    "SB: 2 Fire/Ice\n"
    "MB: 1 Sol Ring\n"
)


def test_info_json_without_card_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    deck = _deck(tmp_path, _ZONED_DECK)
    result = CliRunner().invoke(main, ["info", "--json", str(deck)])
    assert result.exit_code == 0, result.output
    assert _doc(result) == {
        "schema": "vimtg.info/1",
        "file": str(deck),
        "name": "Lurrus Burn",
        "format": None,
        "format_source": None,
        "zones": {
            "commander": {"cards": 0, "unique": 0},
            "companion": {"cards": 1, "unique": 1},
            "main": {"cards": 56, "unique": 2},
            "sideboard": {"cards": 2, "unique": 1},
            "maybeboard": {"cards": 1, "unique": 1},
        },
        "stats": None,
    }


def test_info_json_names_the_default_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vimtg.config.paths import config_dir

    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    config_dir().mkdir(parents=True, exist_ok=True)
    (config_dir() / "config.toml").write_text(
        '[editor]\ndefault_format = "modern"\n', encoding="utf-8"
    )
    deck = _deck(tmp_path, "4 Lightning Bolt\n")
    doc = _doc(CliRunner().invoke(main, ["info", "--json", str(deck)]))
    assert (doc["format"], doc["format_source"]) == ("modern", "default_format")


def test_info_json_stats_with_card_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_repo: CardRepository
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: sample_repo)
    deck = _deck(
        tmp_path,
        "// Format: modern\n4 Lightning Bolt\n4 Goblin Guide\n52 Mountain\n",
    )
    result = CliRunner().invoke(main, ["info", "--json", str(deck)])
    assert result.exit_code == 0, result.output
    doc = _doc(result)
    assert (doc["format"], doc["format_source"]) == ("modern", "deck")
    stats = doc["stats"]
    assert stats["total_cards"] == 60
    assert stats["land_count"] == 52
    assert stats["average_cmc"] == 1.0
    assert stats["types"] == {"creature": 4, "instant": 4, "land": 52}
    assert stats["mana_curve"][1] == 8
    # 4 Bolt at 1.50 and 4 Goblin Guide at 3.50; Mountain has no price
    assert (stats["price"], stats["price_source"]) == (20.0, "usd")


# --- search ---


def test_search_json_lists_full_cards(
    loaded_search_repo: CardRepository,
) -> None:
    result = CliRunner().invoke(main, ["search", "--json", '!"Lightning Bolt"'])
    assert result.exit_code == 0, result.output
    assert _doc(result) == {
        "schema": "vimtg.search/1",
        "query": '!"Lightning Bolt"',
        "cards": [
            {
                "name": "Lightning Bolt",
                "mana_cost": "{R}",
                "mana_value": 1.0,
                "type_line": "Instant",
                "colors": ["R"],
                "color_identity": ["R"],
                "set": "sta",
                "rarity": "uncommon",
                "oracle_text": "Lightning Bolt deals 3 damage to any target.",
                "prices": {
                    "usd": 1.5, "usd_foil": 4.0, "eur": 1.2, "eur_foil": None, "tix": 0.5,
                },
                "legal_formats": ["commander", "legacy", "modern"],
            }
        ],
    }


def test_search_json_no_results_is_an_empty_list(
    loaded_search_repo: CardRepository,
) -> None:
    result = CliRunner().invoke(main, ["search", "--json", "zzzznothing"])
    assert result.exit_code == 0, result.output
    assert _doc(result)["cards"] == []


def test_search_json_keeps_notes_on_stderr(
    loaded_search_repo: CardRepository,
) -> None:
    result = CliRunner().invoke(main, ["search", "--json", "otag:ramp"])
    assert result.exit_code == 0, result.output
    assert _doc(result)["cards"] == []
    assert "oracle tags not synced" in result.stderr


@pytest.fixture
def loaded_search_repo(
    sample_repo: CardRepository, monkeypatch: pytest.MonkeyPatch
) -> CardRepository:
    monkeypatch.setattr(cli, "_make_card_repo", lambda: sample_repo)
    return sample_repo


# --- missing ---

_MISSING_DECK = (
    "// Deck: Burn\n"
    "4 Lightning Bolt\n"
    "2 Lava Spike\n"
    "20 Mountain\n"
    "SB: 3 Rest in Peace\n"
)


def _collection(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "manabox.csv"
    path.write_text("Name,Quantity\n" + rows, encoding="utf-8")
    return path


def test_missing_json_lists_entries_and_totals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_repo: CardRepository
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: sample_repo)
    deck = _deck(tmp_path, _MISSING_DECK)
    csv = _collection(tmp_path, "Lightning Bolt,3\nMountain,20\n")
    result = CliRunner().invoke(
        main, ["missing", "--json", str(deck), "--collection", str(csv)]
    )
    assert result.exit_code == 0, result.output
    assert _doc(result) == {
        "schema": "vimtg.missing/1",
        "file": str(deck),
        "collection": str(csv),
        "cards": [
            {"name": "Lightning Bolt", "zone": "main", "needed": 4, "owned": 3,
             "missing": 1, "price": 1.5},
            {"name": "Lava Spike", "zone": "main", "needed": 2, "owned": 0,
             "missing": 2, "price": 0.5},
            {"name": "Rest in Peace", "zone": "sideboard", "needed": 3, "owned": 0,
             "missing": 3, "price": 4.0},
        ],
        "totals": {
            "needed": 29, "owned": 23, "missing": 6, "missing_unique": 3,
            "cost_to_complete": 14.5, "unpriced_unique": 0, "price_source": "usd",
        },
    }


def test_missing_json_without_card_data_has_null_prices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    deck = _deck(tmp_path, _MISSING_DECK)
    csv = _collection(tmp_path, "Lightning Bolt,4\nLava Spike,2\nMountain,20\n")
    result = CliRunner().invoke(
        main, ["missing", "--json", str(deck), "--collection", str(csv)]
    )
    assert result.exit_code == 0, result.output
    doc = _doc(result)
    assert doc["cards"] == [
        {"name": "Rest in Peace", "zone": "sideboard", "needed": 3, "owned": 0,
         "missing": 3, "price": None},
    ]
    assert doc["totals"]["cost_to_complete"] is None
    assert "no card database" in result.stderr


def test_missing_json_nothing_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_try_card_repo", lambda: None)
    deck = _deck(tmp_path, "4 Lightning Bolt\n")
    csv = _collection(tmp_path, "Lightning Bolt,4\n")
    result = CliRunner().invoke(
        main, ["missing", "--json", str(deck), "--collection", str(csv)]
    )
    assert result.exit_code == 0, result.output
    doc = _doc(result)
    assert doc["cards"] == []
    assert doc["totals"]["missing"] == 0


def test_search_json_unknown_set_is_null() -> None:
    from vimtg.cli_json import search_doc

    card = Card.from_scryfall(
        {"id": "x", "name": "Goblin Token Maker", "type_line": "Creature — Goblin"}
    )
    (doc,) = search_doc("goblin", [card])["cards"]
    assert doc["set"] is None
    assert doc["prices"]["usd"] is None

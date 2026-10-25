"""`vimtg combos deck.deck [--json]`: combos through Commander Spellbook."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from click.testing import CliRunner

from vimtg.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "spellbook" / "find_my_combos_thassa.json"
POST = "vimtg.services.spellbook.httpx.post"

_DECK = "1 Thassa's Oracle\n1 Demonic Consultation\n1 Sol Ring\n"


@pytest.fixture(autouse=True)
def _live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIMTG_NO_SPELLBOOK", raising=False)
    monkeypatch.delenv("VIMTG_SPELLBOOK_FIXTURE", raising=False)


def _deck(tmp_path: Path) -> Path:
    path = tmp_path / "thoracle.deck"
    path.write_text(_DECK, encoding="utf-8")
    return path


def _ok() -> httpx.Response:
    return httpx.Response(
        200,
        json=json.loads(FIXTURE.read_text(encoding="utf-8")),
        request=httpx.Request("POST", "https://backend.commanderspellbook.com/find-my-combos"),
    )


def _run(*args: str) -> Any:
    return CliRunner().invoke(main, ["combos", *args])


def test_text_lists_combos_then_one_away_then_credit(tmp_path: Path) -> None:
    with patch(POST, return_value=_ok()):
        result = _run(str(_deck(tmp_path)))
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0] == "In this deck (1):"
    assert lines[1] == (
        "  742-1295  Demonic Consultation + Thassa's Oracle"
        "  →  Exile your library, Win the game"
    )
    assert lines[2] == "One card away (3):"
    assert lines[3].startswith("  513-5034--46  Hullbreaker Horror + Sol Ring  →  ")
    assert lines[3].endswith("  (add Hullbreaker Horror)")
    assert lines[4].startswith("  1295-3093  Tainted Pact + Thassa's Oracle  →  Win the game")
    assert lines[-1] == "Combo data from Commander Spellbook: https://commanderspellbook.com"


def test_json_document(tmp_path: Path) -> None:
    path = _deck(tmp_path)
    with patch(POST, return_value=_ok()):
        result = _run(str(path), "--json")
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["schema"] == "vimtg.combos/1"
    assert doc["file"] == str(path)
    assert doc["note"] is None
    assert doc["source"] == {
        "name": "Commander Spellbook", "url": "https://commanderspellbook.com",
    }
    combo = doc["included"][0]
    assert combo == {
        "id": "742-1295",
        "url": "https://commanderspellbook.com/combo/742-1295/",
        "cards": ["Demonic Consultation", "Thassa's Oracle"],
        "produces": ["Exile your library", "Win the game"],
        "missing": [],
        "identity": "UB",
        "mana_needed": "{U}{U}{B}",
        "popularity": 149825,
        "description": combo["description"],
    }
    assert combo["description"].startswith("Cast Demonic Consultation")
    assert [c["missing"] for c in doc["one_away"]] == [
        ["Hullbreaker Horror"], ["Tainted Pact"], ["Tidespout Tyrant"],
    ]


def test_lookup_failure_exits_1(tmp_path: Path) -> None:
    with patch(POST, side_effect=httpx.ConnectError("boom")):
        result = _run(str(_deck(tmp_path)))
    assert result.exit_code == 1
    assert "offline" in result.stderr
    assert result.stdout == ""


def test_opt_out_exits_1_with_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIMTG_NO_SPELLBOOK", "1")
    with patch(POST, side_effect=AssertionError("network hit")):
        result = _run(str(_deck(tmp_path)))
    assert result.exit_code == 1
    assert "VIMTG_NO_SPELLBOOK" in result.stderr


def test_note_goes_to_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIMTG_SPELLBOOK_FIXTURE", str(FIXTURE))
    result = _run(str(_deck(tmp_path)))
    assert result.exit_code == 0
    assert "VIMTG_SPELLBOOK_FIXTURE" in result.stderr
    assert "VIMTG_SPELLBOOK_FIXTURE" not in result.stdout


def test_json_carries_the_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIMTG_SPELLBOOK_FIXTURE", str(FIXTURE))
    result = _run(str(_deck(tmp_path)), "--json")
    assert "VIMTG_SPELLBOOK_FIXTURE" in json.loads(result.stdout)["note"]


def test_no_combos_says_none(tmp_path: Path) -> None:
    empty = httpx.Response(
        200,
        json={"results": {"included": [], "almostIncluded": []}},
        request=httpx.Request("POST", "https://x"),
    )
    with patch(POST, return_value=empty):
        result = _run(str(_deck(tmp_path)))
    assert result.stdout.splitlines()[:4] == [
        "In this deck (0):", "  (none)", "One card away (0):", "  (none)",
    ]

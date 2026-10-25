"""Commander Spellbook combo lookups, against a recorded response."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from vimtg import __version__
from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.deck import Deck
from vimtg.services.spellbook import (
    SpellbookClient,
    SpellbookError,
    combo_url,
    parse_report,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "spellbook" / "find_my_combos_thassa.json"
POST = "vimtg.services.spellbook.httpx.post"

_DECK = (
    "// Format: vintage\n"
    "1 Thassa's Oracle\n"
    "1 Demonic Consultation\n"
    "1 Sol Ring\n"
    "SB: 1 Tainted Pact\n"
)
_DECK_NAMES = frozenset({"Thassa's Oracle", "Demonic Consultation", "Sol Ring"})


def _recorded() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def _deck(text: str = _DECK) -> Deck:
    return parse_deck_text(text)


def _response(status: int = 200, payload: object | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json=_recorded() if payload is None else payload,
        request=httpx.Request("POST", "https://backend.commanderspellbook.com/find-my-combos"),
    )


@pytest.fixture(autouse=True)
def _live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIMTG_NO_SPELLBOOK", raising=False)
    monkeypatch.delenv("VIMTG_SPELLBOOK_FIXTURE", raising=False)


def _combo(combo_id: str, names: list[str], popularity: int | None = 10) -> dict[str, Any]:
    return {
        "id": combo_id,
        "uses": [{"card": {"name": n}, "quantity": 1} for n in names],
        "produces": [{"feature": {"name": "Infinite mana"}, "quantity": 1}],
        "identity": "R",
        "popularity": popularity,
    }


def _payload(included: list[Any], almost: list[Any]) -> dict[str, Any]:
    return {
        "count": None, "next": None, "previous": None,
        "results": {"identity": "R", "included": included, "almostIncluded": almost},
    }


class TestParseRecordedResponse:
    def test_included_combo(self) -> None:
        report = parse_report(_recorded(), _DECK_NAMES)
        assert len(report.included) == 1
        combo = report.included[0]
        assert combo.id == "742-1295"
        assert set(combo.cards) == {"Thassa's Oracle", "Demonic Consultation"}
        assert combo.produces == ("Exile your library", "Win the game")
        assert combo.identity == "UB"
        assert combo.mana_needed == "{U}{U}{B}"
        assert combo.popularity == 149825
        assert combo.description.startswith("Cast Demonic Consultation")
        assert combo.missing == ()

    def test_one_away_is_almost_included_sorted_by_popularity(self) -> None:
        report = parse_report(_recorded(), _DECK_NAMES)
        assert [c.id for c in report.one_away] == ["513-5034--46", "1295-3093", "542-5034"]
        assert [c.missing for c in report.one_away] == [
            ("Hullbreaker Horror",), ("Tainted Pact",), ("Tidespout Tyrant",),
        ]

    def test_colour_adding_bucket_is_dropped(self) -> None:
        report = parse_report(_recorded(), _DECK_NAMES)
        ids = {c.id for c in report.included + report.one_away}
        assert "1295-4400" not in ids  # almostIncludedByAddingColors

    def test_included_sorted_by_popularity(self) -> None:
        data = _payload(
            [
                _combo("a", ["X", "Y"], 5),
                _combo("b", ["X", "Z"], 50),
                _combo("c", ["Y", "Z"], None),
            ],
            [],
        )
        report = parse_report(data, frozenset({"X", "Y", "Z"}))
        assert [c.id for c in report.included] == ["b", "a", "c"]


class TestOneAwayFilter:
    def test_two_missing_cards_is_not_one_away(self) -> None:
        data = _payload([], [_combo("two", ["Krenko, Mob Boss", "A", "B"])])
        report = parse_report(data, frozenset({"Krenko, Mob Boss"}))
        assert report.one_away == ()

    def test_names_match_case_insensitively_and_by_front_face(self) -> None:
        data = _payload([], [
            _combo("dfc", [
                "Toralf, God of Fury // Toralf's Hammer", "Blasphemous Act", "Repercussion",
            ]),
        ])
        report = parse_report(data, frozenset({"toralf, god of fury", "Blasphemous Act"}))
        assert [c.missing for c in report.one_away] == [("Repercussion",)]

    def test_malformed_combos_are_skipped(self) -> None:
        data = _payload(
            [{"id": 3}, "junk", {"id": "ok", "uses": [{"card": {"name": "X"}}], "produces": "?"}],
            [None],
        )
        report = parse_report(data, frozenset({"X"}))
        assert [(c.id, c.produces, c.popularity) for c in report.included] == [("ok", (), 0)]

    def test_a_payload_without_results_raises(self) -> None:
        with pytest.raises(SpellbookError):
            parse_report({"detail": "nope"}, frozenset())


def test_combo_url() -> None:
    assert combo_url("742-1295") == "https://commanderspellbook.com/combo/742-1295/"


class TestRequest:
    def test_sends_main_and_commander_zones_with_user_agent(self, tmp_path: Path) -> None:
        deck = _deck(
            "// Format: commander\n"
            "CMD: 1 Krenko, Mob Boss\n"
            "1 Skirk Prospector\n"
            "1 Goblin Warchief\n"
            "2 Mountain\n"
            "1 Mountain\n"
            "SB: 1 Repercussion\n"
        )
        with patch(POST, return_value=_response()) as post:
            SpellbookClient(cache_dir=tmp_path).find(deck)
        assert post.call_count == 1
        assert post.call_args.args[0] == "https://backend.commanderspellbook.com/find-my-combos"
        body = post.call_args.kwargs["json"]
        assert body["commanders"] == [{"card": "Krenko, Mob Boss", "quantity": 1}]
        assert sorted(body["main"], key=lambda e: e["card"]) == [
            {"card": "Goblin Warchief", "quantity": 1},
            {"card": "Mountain", "quantity": 3},
            {"card": "Skirk Prospector", "quantity": 1},
        ]
        assert post.call_args.kwargs["headers"]["User-Agent"] == f"vimtg/{__version__}"

    def test_find_reports_combos(self, tmp_path: Path) -> None:
        with patch(POST, return_value=_response()):
            report = SpellbookClient(cache_dir=tmp_path).find(_deck())
        assert [c.id for c in report.included] == ["742-1295"]
        assert report.note == ""


class TestCache:
    def test_second_lookup_is_served_from_cache(self, tmp_path: Path) -> None:
        client = SpellbookClient(cache_dir=tmp_path)
        with patch(POST, return_value=_response()):
            client.find(_deck())
        with patch(POST, side_effect=AssertionError("network hit despite cache")):
            report = client.find(_deck())
        assert [c.id for c in report.included] == ["742-1295"]

    def test_card_edit_invalidates_the_cache(self, tmp_path: Path) -> None:
        client = SpellbookClient(cache_dir=tmp_path)
        with patch(POST, return_value=_response()):
            client.find(_deck())
        edited = _deck(_DECK.replace("1 Sol Ring", "2 Sol Ring"))
        with patch(POST, return_value=_response()) as post:
            client.find(edited)
        assert post.call_count == 1

    def test_line_order_and_sideboard_do_not_invalidate(self, tmp_path: Path) -> None:
        client = SpellbookClient(cache_dir=tmp_path)
        with patch(POST, return_value=_response()):
            client.find(_deck())
        reordered = _deck(
            "1 Sol Ring\n1 Demonic Consultation\n1 Thassa's Oracle\nSB: 4 Duress\n"
        )
        with patch(POST, side_effect=AssertionError("network hit despite cache")):
            client.find(reordered)

    def _age_cache(self, tmp_path: Path, days: float) -> None:
        files = list((tmp_path / "spellbook").glob("*.json"))
        assert len(files) == 1
        old = time.time() - days * 86400
        os.utime(files[0], (old, old))

    def test_expired_cache_is_refetched(self, tmp_path: Path) -> None:
        client = SpellbookClient(cache_dir=tmp_path)
        with patch(POST, return_value=_response()):
            client.find(_deck())
        self._age_cache(tmp_path, days=8)
        with patch(POST, return_value=_response()) as post:
            report = client.find(_deck())
        assert post.call_count == 1
        assert report.note == ""

    def test_corrupt_cache_is_a_miss(self, tmp_path: Path) -> None:
        client = SpellbookClient(cache_dir=tmp_path)
        with patch(POST, return_value=_response()):
            client.find(_deck())
        next((tmp_path / "spellbook").glob("*.json")).write_text("{not json")
        with patch(POST, return_value=_response()) as post:
            report = client.find(_deck())
        assert post.call_count == 1
        assert report.included

    def test_rate_limited_with_cache_returns_cached_report(self, tmp_path: Path) -> None:
        client = SpellbookClient(cache_dir=tmp_path)
        with patch(POST, return_value=_response()):
            client.find(_deck())
        self._age_cache(tmp_path, days=9.5)
        with patch(POST, return_value=_response(status=429, payload={})):
            report = client.find(_deck())
        assert [c.id for c in report.included] == ["742-1295"]
        assert report.note == "cached 9 days ago (Commander Spellbook is rate-limiting)"

    def test_offline_with_cache_returns_cached_report(self, tmp_path: Path) -> None:
        client = SpellbookClient(cache_dir=tmp_path)
        with patch(POST, return_value=_response()):
            client.find(_deck())
        self._age_cache(tmp_path, days=8)
        with patch(POST, side_effect=httpx.ConnectError("boom")):
            report = client.find(_deck())
        assert report.included
        assert report.note == "cached 8 days ago (offline)"


class TestFailures:
    def test_rate_limited_without_cache_raises(self, tmp_path: Path) -> None:
        with (
            patch(POST, return_value=_response(status=429, payload={})),
            pytest.raises(SpellbookError, match="rate-limiting"),
        ):
            SpellbookClient(cache_dir=tmp_path).find(_deck())

    def test_offline_without_cache_raises(self, tmp_path: Path) -> None:
        with (
            patch(POST, side_effect=httpx.ConnectError("boom")),
            pytest.raises(SpellbookError, match="offline"),
        ):
            SpellbookClient(cache_dir=tmp_path).find(_deck())

    def test_rejected_request_raises_with_the_reason(self, tmp_path: Path) -> None:
        body = {"commanders": ["Ensure this field has no more than 12 elements."]}
        with (
            patch(POST, return_value=_response(status=400, payload=body)),
            pytest.raises(SpellbookError, match="no more than 12"),
        ):
            SpellbookClient(cache_dir=tmp_path).find(_deck())

    def test_rejected_request_does_not_fall_back_to_cache(self, tmp_path: Path) -> None:
        client = SpellbookClient(cache_dir=tmp_path)
        with patch(POST, return_value=_response()):
            client.find(_deck())
        TestCache()._age_cache(tmp_path, days=8)
        with (
            patch(POST, return_value=_response(status=400, payload={})),
            pytest.raises(SpellbookError, match="HTTP 400"),
        ):
            client.find(_deck())

    def test_an_unusable_body_is_not_cached(self, tmp_path: Path) -> None:
        client = SpellbookClient(cache_dir=tmp_path)
        with patch(POST, return_value=_response(payload=["junk"])), pytest.raises(SpellbookError):
            client.find(_deck())
        assert not list(tmp_path.glob("spellbook/*.json"))

    def test_empty_deck_raises_without_a_request(self, tmp_path: Path) -> None:
        with (
            patch(POST, side_effect=AssertionError("network hit")),
            pytest.raises(SpellbookError, match="No cards"),
        ):
            SpellbookClient(cache_dir=tmp_path).find(_deck("SB: 1 Duress\n"))


class TestOptOutAndFixture:
    def test_opt_out_disables_lookups(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VIMTG_NO_SPELLBOOK", "1")
        with (
            patch(POST, side_effect=AssertionError("network hit")),
            pytest.raises(SpellbookError, match="VIMTG_NO_SPELLBOOK"),
        ):
            SpellbookClient(cache_dir=tmp_path).find(_deck())

    def test_fixture_replaces_the_request_and_says_so(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VIMTG_SPELLBOOK_FIXTURE", str(FIXTURE))
        with patch(POST, side_effect=AssertionError("network hit")):
            report = SpellbookClient(cache_dir=tmp_path).find(_deck())
        assert [c.id for c in report.included] == ["742-1295"]
        assert "VIMTG_SPELLBOOK_FIXTURE" in report.note
        assert not list(tmp_path.glob("spellbook/*.json"))

    def test_unreadable_fixture_raises_instead_of_going_live(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VIMTG_SPELLBOOK_FIXTURE", str(tmp_path / "absent.json"))
        with (
            patch(POST, side_effect=AssertionError("network hit")),
            pytest.raises(SpellbookError, match="VIMTG_SPELLBOOK_FIXTURE"),
        ):
            SpellbookClient(cache_dir=tmp_path).find(_deck())

    def test_opt_out_wins_over_a_fixture(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VIMTG_NO_SPELLBOOK", "1")
        monkeypatch.setenv("VIMTG_SPELLBOOK_FIXTURE", str(FIXTURE))
        with pytest.raises(SpellbookError, match="VIMTG_NO_SPELLBOOK"):
            SpellbookClient(cache_dir=tmp_path).find(_deck())


class TestEdges:
    def test_no_cache_dir_still_looks_up(self) -> None:
        with patch(POST, return_value=_response()) as post:
            SpellbookClient(cache_dir=None).find(_deck())
            SpellbookClient(cache_dir=None).find(_deck())
        assert post.call_count == 2

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        bad = httpx.Response(
            200, content=b"<html>", request=httpx.Request("POST", "https://x"),
        )
        with patch(POST, return_value=bad), pytest.raises(SpellbookError, match="invalid JSON"):
            SpellbookClient(cache_dir=tmp_path).find(_deck())

    def test_server_error_with_cache_says_unavailable(self, tmp_path: Path) -> None:
        client = SpellbookClient(cache_dir=tmp_path)
        with patch(POST, return_value=_response()):
            client.find(_deck())
        TestCache()._age_cache(tmp_path, days=8)
        with patch(POST, return_value=_response(status=503, payload={})):
            report = client.find(_deck())
        assert report.note == "cached 8 days ago (Commander Spellbook is unavailable)"

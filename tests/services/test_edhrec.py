"""Tests for the EDHREC recommendations client."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from vimtg.services.edhrec import (
    EdhrecClient,
    EdhrecError,
    build_tabs,
    commander_slug,
    parse_page,
)


def _cardview(name: str, num: int = 100, potential: int = 1000, syn: float = 0.1):
    return {
        "name": name,
        "num_decks": num,
        "potential_decks": potential,
        "synergy": syn,
    }


def _payload(cardlists: list[dict] | None = None, title: str = "Atraxa"):
    if cardlists is None:
        cardlists = [
            {
                "header": "Top Cards",
                "tag": "topcards",
                "cardviews": [_cardview("Sol Ring"), _cardview("Cultivate")],
            },
            {
                "header": "Creatures",
                "tag": "creatures",
                "cardviews": [_cardview("Solemn Simulacrum")],
            },
        ]
    return {"container": {"title": title, "json_dict": {"cardlists": cardlists}}}


class TestCommanderSlug:
    def test_simple_name(self):
        assert commander_slug(["Urza, Lord High Artificer"]) == (
            "urza-lord-high-artificer"
        )

    def test_apostrophes_are_dropped(self):
        assert commander_slug(["K'rrik, Son of Yawgmoth"]) == (
            "krrik-son-of-yawgmoth"
        )

    def test_accents_fold_to_ascii(self):
        assert commander_slug(["Jötun Grunt"]) == "jotun-grunt"

    def test_partner_pair_joins_both_names(self):
        slug = commander_slug(["Thrasios, Triton Hero", "Tymna the Weaver"])
        assert slug == "thrasios-triton-hero-tymna-the-weaver"

    def test_split_card_uses_front_face(self):
        assert commander_slug(["Valki, God of Lies // Tibalt"]) == (
            "valki-god-of-lies"
        )

    def test_no_names_raises(self):
        with pytest.raises(EdhrecError):
            commander_slug(["  "])


class TestParsePage:
    def test_parses_lists_into_tabs(self):
        page = parse_page(_payload())
        assert page.commander == "Atraxa"
        labels = [t.label for t in page.tabs]
        assert labels == ["Top", "Creatures"]
        assert page.tabs[0].cards[0].name == "Sol Ring"

    def test_inclusion_pct(self):
        page = parse_page(_payload())
        assert page.tabs[0].cards[0].inclusion_pct == pytest.approx(10.0)

    def test_malformed_cardviews_are_skipped(self):
        payload = _payload([
            {
                "header": "Creatures",
                "tag": "creatures",
                "cardviews": [
                    _cardview("Good Card"),
                    {"no_name": True},
                    "not-a-dict",
                    {"name": ""},
                ],
            },
        ])
        page = parse_page(payload)
        assert [c.name for c in page.tabs[0].cards] == ["Good Card"]

    def test_non_dict_payload_raises(self):
        with pytest.raises(EdhrecError):
            parse_page(["not", "a", "dict"])

    def test_missing_cardlists_raises(self):
        with pytest.raises(EdhrecError):
            parse_page({"container": {}})

    def test_all_unusable_lists_raises(self):
        with pytest.raises(EdhrecError):
            parse_page(_payload([{"tag": "creatures", "cardviews": []}]))

    def test_commander_fallback_used_without_title(self):
        payload = _payload()
        del payload["container"]["title"]
        page = parse_page(payload, commander_fallback="Fallback Name")
        assert page.commander == "Fallback Name"


class TestBuildTabs:
    def test_merges_artifact_lists_dedup_first_wins(self):
        from vimtg.services.edhrec import EdhrecCard

        a = EdhrecCard("Sol Ring", 1, 10, 0.0)
        b = EdhrecCard("Arcane Signet", 2, 10, 0.0)
        dup = EdhrecCard("sol ring", 3, 10, 0.0)  # case-insensitive dup
        tabs = build_tabs({
            "utilityartifacts": (a,),
            "manaartifacts": (dup, b),
        })
        assert len(tabs) == 1
        assert tabs[0].label == "Artifacts"
        assert [c.name for c in tabs[0].cards] == ["Sol Ring", "Arcane Signet"]

    def test_empty_tabs_dropped(self):
        assert build_tabs({}) == ()


class TestEdhrecClient:
    def _response(self, status: int = 200, payload=None):
        return httpx.Response(
            status_code=status,
            json=payload if payload is not None else _payload(),
            request=httpx.Request("GET", "https://json.edhrec.com/x"),
        )

    def test_fetch_parses_remote_page(self, tmp_path: Path):
        client = EdhrecClient(cache_dir=tmp_path)
        with patch(
            "vimtg.services.edhrec.httpx.get", return_value=self._response()
        ) as mock_get:
            page = client.fetch(["Atraxa, Praetors' Voice"])
        assert page.commander == "Atraxa"
        url = mock_get.call_args.args[0]
        assert url.endswith("/atraxa-praetors-voice.json")

    def test_fetch_writes_and_reuses_cache(self, tmp_path: Path):
        client = EdhrecClient(cache_dir=tmp_path)
        with patch(
            "vimtg.services.edhrec.httpx.get", return_value=self._response()
        ):
            client.fetch(["Atraxa"])
        # Second fetch must not touch the network
        with patch(
            "vimtg.services.edhrec.httpx.get",
            side_effect=AssertionError("network hit despite cache"),
        ):
            page = client.fetch(["Atraxa"])
        assert page.commander == "Atraxa"

    def test_stale_cache_is_refetched(self, tmp_path: Path):
        cache_file = tmp_path / "edhrec" / "atraxa.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps(_payload(title="Stale")))
        old = time.time() - 8 * 86400
        import os

        os.utime(cache_file, (old, old))
        client = EdhrecClient(cache_dir=tmp_path)
        with patch(
            "vimtg.services.edhrec.httpx.get",
            return_value=self._response(payload=_payload(title="Fresh")),
        ):
            page = client.fetch(["Atraxa"])
        assert page.commander == "Fresh"

    def test_http_404_raises_edhrec_error(self, tmp_path: Path):
        client = EdhrecClient(cache_dir=tmp_path)
        with patch(
            "vimtg.services.edhrec.httpx.get",
            return_value=self._response(status=404),
        ), pytest.raises(EdhrecError, match="No EDHREC page"):
            client.fetch(["Nonexistent Commander"])

    def test_network_error_raises_edhrec_error(self, tmp_path: Path):
        client = EdhrecClient(cache_dir=tmp_path)
        with patch(
            "vimtg.services.edhrec.httpx.get",
            side_effect=httpx.ConnectError("boom"),
        ), pytest.raises(EdhrecError, match="request failed"):
            client.fetch(["Atraxa"])

    def test_no_cache_dir_still_fetches(self):
        client = EdhrecClient(cache_dir=None)
        with patch(
            "vimtg.services.edhrec.httpx.get", return_value=self._response()
        ):
            page = client.fetch(["Atraxa"])
        assert page.tabs

"""Tests for the online decklist source fetchers (ported from cod-sync,
adapted to vimtg's five-zone deck model and inline categories)."""

from __future__ import annotations

import html
import json

import pytest

from vimtg.domain.deck import DeckSection
from vimtg.services.deck_sources import (
    DeckSourceError,
    fetch_deck,
    is_deck_url,
    parse_archidekt,
    parse_manabox_page,
    parse_moxfield,
)

# ── URL dispatch ───────────────────────────────────────────────────


class TestIsDeckUrl:
    def test_known_hosts(self) -> None:
        assert is_deck_url("https://moxfield.com/decks/abc")
        assert is_deck_url("https://www.moxfield.com/decks/abc")
        assert is_deck_url("https://archidekt.com/decks/123/slug")
        assert is_deck_url("https://manabox.app/decks/xyz")

    def test_non_urls(self) -> None:
        assert not is_deck_url("deck.txt")
        assert not is_deck_url("~/decks/burn.deck")

    def test_unknown_host_is_still_a_url(self) -> None:
        # Dispatchable as a URL — fetch_deck then reports the bad host
        assert is_deck_url("https://example.com/decks/abc")


class TestFetchDispatch:
    def test_unsupported_host_raises(self) -> None:
        with pytest.raises(DeckSourceError, match="[Uu]nsupported"):
            fetch_deck("https://example.com/decks/abc")

    def test_bad_moxfield_url_raises(self) -> None:
        with pytest.raises(DeckSourceError, match="deck id"):
            fetch_deck("https://moxfield.com/about")


# ── Moxfield ───────────────────────────────────────────────────────


_MOXFIELD = {
    "name": " Burn ",
    "boards": {
        "mainboard": {
            "cards": {
                "a": {"quantity": 4, "card": {"name": "Lightning Bolt"}},
                "b": {"quantity": 20, "card": {"name": "Mountain"}},
            }
        },
        "sideboard": {
            "cards": {"c": {"quantity": 2, "card": {"name": "Rest in Peace"}}}
        },
        "commanders": {
            "cards": {
                "d": {"quantity": 1, "card": {"name": "Atraxa, Praetors' Voice"}}
            }
        },
        "companions": {
            "cards": {
                "e": {"quantity": 1, "card": {"name": "Lurrus of the Dream-Den"}}
            }
        },
        "maybeboard": {"cards": {"f": {"quantity": 1, "card": {"name": "Opt"}}}},
    },
}


class TestParseMoxfield:
    def test_name_and_zones(self) -> None:
        remote = parse_moxfield(_MOXFIELD)
        assert remote.name == "Burn"
        by_zone = {
            (e.section, e.card_name): e.quantity for e in remote.deck.entries
        }
        assert by_zone[(DeckSection.MAIN, "Lightning Bolt")] == 4
        assert by_zone[(DeckSection.SIDEBOARD, "Rest in Peace")] == 2
        assert by_zone[(DeckSection.COMMANDER, "Atraxa, Praetors' Voice")] == 1
        assert by_zone[(DeckSection.COMPANION, "Lurrus of the Dream-Den")] == 1

    def test_maybeboard_kept(self) -> None:
        # vimtg has a real maybeboard zone — unlike Cockatrice, the
        # maybeboard survives the import as MB: lines
        remote = parse_moxfield(_MOXFIELD)
        maybe = [
            e for e in remote.deck.entries
            if e.section == DeckSection.MAYBEBOARD
        ]
        assert [(e.card_name, e.quantity) for e in maybe] == [("Opt", 1)]

    def test_zero_quantity_and_nameless_skipped(self) -> None:
        data = {
            "name": "x",
            "boards": {
                "mainboard": {
                    "cards": {
                        "a": {"quantity": 0, "card": {"name": "Opt"}},
                        "b": {"quantity": 2, "card": {}},
                    }
                }
            },
        }
        remote = parse_moxfield(data)
        assert remote.deck.entries == ()


# ── Archidekt ──────────────────────────────────────────────────────


_ARCHIDEKT = {
    "name": "Krenko Goblins",
    "categories": [
        {"name": "Maybeboard", "includedInDeck": False},
        {"name": "Ramp Package", "includedInDeck": True},
    ],
    "cards": [
        {
            "quantity": 1,
            "categories": ["Commander"],
            "card": {"oracleCard": {"name": "Krenko, Mob Boss"}},
        },
        {
            # Secondary 'Sideboard' label must NOT re-zone the card
            "quantity": 1,
            "categories": ["Ramp Package", "Sideboard"],
            "card": {"oracleCard": {"name": "Sol Ring"}},
        },
        {
            "quantity": 2,
            "categories": ["Maybeboard"],
            "card": {"oracleCard": {"name": "Opt"}},
        },
        {
            # Type-named category is Archidekt's default grouping, not
            # a user category — it must not force @creature tokens
            "quantity": 3,
            "categories": ["Creature"],
            "card": {"oracleCard": {"name": "Goblin Guide"}},
        },
        {
            "quantity": 4,
            "categories": ["Sideboard"],
            "card": {"oracleCard": {"name": "Pyroblast"}},
        },
    ],
}


class TestParseArchidekt:
    def test_zones(self) -> None:
        remote = parse_archidekt(_ARCHIDEKT)
        assert remote.name == "Krenko Goblins"
        by_zone = {
            (e.section, e.card_name): e for e in remote.deck.entries
        }
        assert (DeckSection.COMMANDER, "Krenko, Mob Boss") in by_zone
        assert (DeckSection.MAIN, "Sol Ring") in by_zone
        assert (DeckSection.SIDEBOARD, "Pyroblast") in by_zone
        assert by_zone[(DeckSection.MAYBEBOARD, "Opt")].quantity == 2

    def test_user_category_becomes_inline_category(self) -> None:
        remote = parse_archidekt(_ARCHIDEKT)
        sol = next(
            e for e in remote.deck.entries if e.card_name == "Sol Ring"
        )
        assert sol.category == "ramp-package"

    def test_type_category_is_dropped(self) -> None:
        remote = parse_archidekt(_ARCHIDEKT)
        guide = next(
            e for e in remote.deck.entries if e.card_name == "Goblin Guide"
        )
        assert guide.category == ""


# ── ManaBox ────────────────────────────────────────────────────────


def _manabox_page(deck: dict) -> str:
    def enc(value):  # Astro [type, value] encoding
        if isinstance(value, dict):
            return [0, {k: enc(v) for k, v in value.items()}]
        if isinstance(value, list):
            return [1, [enc(v) for v in value]]
        return [0, value]

    props = json.dumps({"deck": enc(deck)})
    return (
        "<html><body><astro-island uid=\"x\" "
        'component-export="Main" '
        f'props="{html.escape(props, quote=True)}" ></astro-island></body></html>'
    )


class TestParseManabox:
    def test_zones_from_board_categories(self) -> None:
        page = _manabox_page(
            {
                "name": "Mono Red",
                "cards": [
                    {"name": "Lightning Bolt", "quantity": 4, "boardCategory": 3},
                    {"name": "Rest in Peace", "quantity": 2, "boardCategory": 4},
                    {"name": "Krenko, Mob Boss", "quantity": 1, "boardCategory": 0},
                    {"name": "Opt", "quantity": 1, "boardCategory": 5},
                ],
            }
        )
        remote = parse_manabox_page("https://manabox.app/decks/x", page)
        assert remote.name == "Mono Red"
        by_zone = {
            (e.section, e.card_name): e.quantity for e in remote.deck.entries
        }
        assert by_zone[(DeckSection.MAIN, "Lightning Bolt")] == 4
        assert by_zone[(DeckSection.SIDEBOARD, "Rest in Peace")] == 2
        assert by_zone[(DeckSection.COMMANDER, "Krenko, Mob Boss")] == 1
        assert by_zone[(DeckSection.MAYBEBOARD, "Opt")] == 1

    def test_missing_island_raises(self) -> None:
        with pytest.raises(DeckSourceError, match="deck data"):
            parse_manabox_page("https://manabox.app/decks/x", "<html></html>")


# ── Network wrapper (stubbed httpx) ────────────────────────────────


class _Resp:
    def __init__(self, data: object, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> object:
        return self._data


class TestFetchNetwork:
    def test_moxfield_fetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import vimtg.services.deck_sources as ds

        def fake_get(url: str, **kwargs: object) -> _Resp:
            assert "api2.moxfield.com" in url
            return _Resp(_MOXFIELD)

        monkeypatch.setattr(ds.httpx, "get", fake_get)
        remote = fetch_deck("https://moxfield.com/decks/abc123")
        assert remote.name == "Burn"

    def test_http_error_maps_to_source_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        import vimtg.services.deck_sources as ds

        def fake_get(url: str, **kwargs: object) -> _Resp:
            raise httpx.ConnectError("boom")

        monkeypatch.setattr(ds.httpx, "get", fake_get)
        with pytest.raises(DeckSourceError, match="request failed"):
            fetch_deck("https://moxfield.com/decks/abc123")

    def test_http_status_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import vimtg.services.deck_sources as ds

        monkeypatch.setattr(
            ds.httpx, "get", lambda url, **kw: _Resp({}, status_code=404)
        )
        with pytest.raises(DeckSourceError, match="404"):
            fetch_deck("https://archidekt.com/decks/12345")


# ── Shared text-list parser (deckstats/tappedout/goldfish) ─────────


class TestParseDecklistText:
    def test_basic_zones_and_prefixes(self) -> None:
        from vimtg.services.deck_sources import parse_decklist_text

        remote = parse_decklist_text(
            "//Main\n"
            "1 Atraxa, Praetors' Voice #!Commander\n"
            "4 Cultivate\n"
            "//Lands (24)\n"          # grouping header — not a zone
            "24 Forest\n"
            "//Sideboard\n"
            "SB: 2 Duress\n"
            "3 Naturalize\n",          # zone carried from the header
            name="Atraxa",
        )
        assert remote.name == "Atraxa"
        by_zone = {
            (e.section, e.card_name): e.quantity for e in remote.deck.entries
        }
        assert by_zone[(DeckSection.COMMANDER, "Atraxa, Praetors' Voice")] == 1
        assert by_zone[(DeckSection.MAIN, "Cultivate")] == 4
        assert by_zone[(DeckSection.MAIN, "Forest")] == 24
        assert by_zone[(DeckSection.SIDEBOARD, "Duress")] == 2
        assert by_zone[(DeckSection.SIDEBOARD, "Naturalize")] == 3

    def test_arena_style_set_suffix_stripped(self) -> None:
        from vimtg.services.deck_sources import parse_decklist_text

        remote = parse_decklist_text("4 Lightning Bolt (STA) 42\n", name="")
        assert remote.deck.entries[0].card_name == "Lightning Bolt"

    def test_x_quantity_and_hash_comment(self) -> None:
        from vimtg.services.deck_sources import parse_decklist_text

        remote = parse_decklist_text(
            "4x Lightning Bolt # burn them all\n", name=""
        )
        entry = remote.deck.entries[0]
        assert (entry.card_name, entry.quantity) == ("Lightning Bolt", 4)

    def test_blank_line_splits_sideboard_when_asked(self) -> None:
        from vimtg.services.deck_sources import parse_decklist_text

        text = "4 Lightning Bolt\n20 Mountain\n\n2 Duress\n"
        remote = parse_decklist_text(text, name="", blank_splits=True)
        by_zone = {
            (e.section, e.card_name): e.quantity for e in remote.deck.entries
        }
        assert by_zone[(DeckSection.MAIN, "Mountain")] == 20
        assert by_zone[(DeckSection.SIDEBOARD, "Duress")] == 2

    def test_blank_lines_neutral_by_default(self) -> None:
        from vimtg.services.deck_sources import parse_decklist_text

        text = "4 Lightning Bolt\n\n20 Mountain\n"
        remote = parse_decklist_text(text, name="")
        assert all(
            e.section == DeckSection.MAIN for e in remote.deck.entries
        )

    def test_zone_word_headers(self) -> None:
        from vimtg.services.deck_sources import parse_decklist_text

        text = (
            "Commander\n1 Krenko, Mob Boss\n"
            "Deck\n4 Lightning Bolt\n"
            "Sideboard:\n2 Duress\n"
            "Maybeboard\n1 Opt\n"
        )
        remote = parse_decklist_text(text, name="")
        by_zone = {
            (e.section, e.card_name): e.quantity for e in remote.deck.entries
        }
        assert (DeckSection.COMMANDER, "Krenko, Mob Boss") in by_zone
        assert (DeckSection.MAIN, "Lightning Bolt") in by_zone
        assert (DeckSection.SIDEBOARD, "Duress") in by_zone
        assert (DeckSection.MAYBEBOARD, "Opt") in by_zone


# ── Deckstats / TappedOut / MTGGoldfish dispatch ───────────────────


class TestNewSourceDispatch:
    def test_deckstats_fetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import vimtg.services.deck_sources as ds

        payload = {
            "success": True,
            "name": "Atraxa Superfriends",
            "list": "//Main\n1 Atraxa, Praetors' Voice #!Commander\n4 Cultivate\n",
        }
        seen = {}

        def fake_get(url: str, **kwargs: object) -> _Resp:
            seen["url"] = url
            return _Resp(payload)

        monkeypatch.setattr(ds.httpx, "get", fake_get)
        remote = fetch_deck("https://deckstats.net/decks/12345/678900-atraxa")
        assert "api.php" in seen["url"]
        assert "owner_id=12345" in seen["url"]
        assert "id=678900" in seen["url"]
        assert remote.name == "Atraxa Superfriends"
        commanders = [
            e for e in remote.deck.entries
            if e.section == DeckSection.COMMANDER
        ]
        assert commanders[0].card_name == "Atraxa, Praetors' Voice"

    def test_tappedout_fetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import vimtg.services.deck_sources as ds

        class _TextResp:
            status_code = 200
            text = "4 Lightning Bolt\nSB: 2 Duress\n"

            def json(self) -> object:
                raise ValueError

        seen = {}

        def fake_get(url: str, **kwargs: object) -> _TextResp:
            seen["url"] = url
            return _TextResp()

        monkeypatch.setattr(ds.httpx, "get", fake_get)
        remote = fetch_deck("https://tappedout.net/mtg-decks/krenko-mob-boss/")
        assert seen["url"].endswith("?fmt=dec")
        assert remote.name == "krenko mob boss"
        by_zone = {
            (e.section, e.card_name): e.quantity for e in remote.deck.entries
        }
        assert by_zone[(DeckSection.MAIN, "Lightning Bolt")] == 4
        assert by_zone[(DeckSection.SIDEBOARD, "Duress")] == 2

    def test_mtggoldfish_fetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import vimtg.services.deck_sources as ds

        class _TextResp:
            status_code = 200
            text = "4 Lightning Bolt\n20 Mountain\n\n2 Duress\n"

            def json(self) -> object:
                raise ValueError

        seen = {}

        def fake_get(url: str, **kwargs: object) -> _TextResp:
            seen["url"] = url
            return _TextResp()

        monkeypatch.setattr(ds.httpx, "get", fake_get)
        remote = fetch_deck("https://www.mtggoldfish.com/deck/6543210#paper")
        assert "deck/download/6543210" in seen["url"]
        by_zone = {
            (e.section, e.card_name): e.quantity for e in remote.deck.entries
        }
        assert by_zone[(DeckSection.MAIN, "Mountain")] == 20
        assert by_zone[(DeckSection.SIDEBOARD, "Duress")] == 2

    def test_bad_deckstats_url(self) -> None:
        with pytest.raises(DeckSourceError, match="deck id"):
            fetch_deck("https://deckstats.net/decks/folder/")

    def test_bad_goldfish_url(self) -> None:
        with pytest.raises(DeckSourceError, match="deck id"):
            fetch_deck("https://www.mtggoldfish.com/metagame/modern")

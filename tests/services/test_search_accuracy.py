"""Search additions against real-shaped Scryfall cards: produces:,
is:permanent/spell/hybrid/phyrexian, stat-vs-stat comparisons, back-face
P/T, kw:partner, typographic quotes, order:/direction:, full split costs,
and clear errors for what is still unsupported."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card
from vimtg.domain.search import (
    FieldCompare,
    ProducesMatch,
    SearchOrder,
    parse_search,
    parse_search_with_order,
)
from vimtg.services.search_service import SearchService, SearchSyntaxError

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def svc(
    db_factory: Callable[..., Database], real_shape_cards: list[dict[str, Any]]
) -> SearchService:
    raw: list[dict[str, Any]] = list(real_shape_cards)
    for name in ("scryfall_mana_analytics.json", "scryfall_mana_accuracy.json"):
        raw += json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    repo = CardRepository(db_factory())
    repo.replace_all([Card.from_scryfall(d) for d in raw])
    return SearchService(card_repo=repo)


def names(svc: SearchService, query: str) -> set[str]:
    return {c.name for c in svc.search(query, limit=500)}


class TestParser:
    def test_field_compare(self) -> None:
        assert parse_search("pow>tou") == FieldCompare("power", ">", "toughness")
        assert parse_search("tou<=mv") == FieldCompare("toughness", "<=", "cmc")

    def test_produces(self) -> None:
        assert parse_search("produces:rg") == ProducesMatch(">=", frozenset("RG"))
        assert parse_search("produces=c") == ProducesMatch("=", frozenset("C"))
        assert parse_search("produces:izzet") == ProducesMatch(">=", frozenset("UR"))
        with pytest.raises(SearchSyntaxError, match="Unknown colour"):
            parse_search("produces:x")

    def test_order(self) -> None:
        node, order = parse_search_with_order("t:elf order:cmc direction:desc")
        assert order == SearchOrder("cmc", True)
        assert parse_search_with_order("t:elf")[1] is None
        with pytest.raises(SearchSyntaxError, match="Unknown sort order"):
            parse_search_with_order("order:banana")
        with pytest.raises(SearchSyntaxError, match="Unknown direction"):
            parse_search_with_order("direction:up")
        with pytest.raises(SearchSyntaxError, match="only supports ':'"):
            parse_search_with_order("order>cmc")
        # still being typed
        assert parse_search_with_order("t:elf order:") == (parse_search("t:elf"), None)

    @pytest.mark.parametrize("key", ["year", "date"])
    def test_unsupported_keys_say_so(self, key: str) -> None:
        with pytest.raises(SearchSyntaxError, match=f"'{key}' is not supported"):
            parse_search(f"{key}>=2020")

    def test_other_unknown_keys_unchanged(self) -> None:
        with pytest.raises(SearchSyntaxError, match="Unknown search key 'foo'"):
            parse_search("foo:bar")


class TestSearch:
    def test_produces(self, svc: SearchService) -> None:
        found = names(svc, "produces:ur")
        assert "Steam Vents" in found and "Watery Grave" not in found
        assert "Llanowar Elves" in names(svc, "produces=g")
        assert "Command Tower" in names(svc, "produces:wubrg")
        within = names(svc, "produces<=ub")
        assert {"Watery Grave", "Island"} <= within and "Steam Vents" not in within
        assert "Lightning Bolt" not in within  # produces nothing
        assert "Watery Grave" in names(svc, "produces!=ur")
        assert "Steam Vents" not in names(svc, "produces!=ur")
        assert "Steam Vents" in names(svc, "produces>u")
        assert "Island" not in names(svc, "produces>u")
        assert "Island" in names(svc, "produces<ub")
        assert "Watery Grave" not in names(svc, "produces<ub")

    def test_is_permanent_and_spell(self, svc: SearchService) -> None:
        perms = names(svc, "is:permanent")
        assert {"Kitchen Finks", "Steam Vents", "Wrenn and Six"} <= perms
        assert "Lightning Bolt" not in perms
        spells = names(svc, "is:spell")
        assert {"Lightning Bolt", "Kitchen Finks"} <= spells
        assert "Steam Vents" not in spells
        # MDFC spell with a land back is a spell (front face)
        assert "Valakut Awakening // Valakut Stoneforge" in spells

    def test_is_hybrid_and_phyrexian(self, svc: SearchService) -> None:
        hybrid = names(svc, "is:hybrid")
        assert {"Kitchen Finks", "Boggart Ram-Gang", "Spectral Procession"} <= hybrid
        assert "Dismember" not in hybrid and "Lightning Bolt" not in hybrid
        phyrexian = names(svc, "is:phyrexian")
        assert {"Dismember", "Gitaxian Probe"} <= phyrexian
        assert "Kitchen Finks" not in phyrexian

    def test_pow_greater_than_tou(self, svc: SearchService) -> None:
        found = names(svc, "pow>tou")
        assert "Kitchen Finks" in found
        assert "Llanowar Elves" not in found
        # Insectile Aberration (back face) is 3/2; the front is 1/1
        assert "Delver of Secrets // Insectile Aberration" in found

    def test_pt_searches_see_back_faces(self, svc: SearchService) -> None:
        assert "Delver of Secrets // Insectile Aberration" in names(svc, "pow>=3")
        assert "Delver of Secrets // Insectile Aberration" in names(svc, "pow=1")

    def test_kw_partner_finds_partner_with(self, svc: SearchService) -> None:
        found = names(svc, "kw:partner")
        assert "Pir, Imaginative Rascal" in found
        assert "Thrasios, Triton Hero" in found
        assert "Pir, Imaginative Rascal" in names(svc, 'kw:"partner with"')

    def test_curly_quotes_fold(self, svc: SearchService) -> None:
        assert "Gaddock Teeg" in names(svc, "o:\u201ccan\u2019t be cast\u201d")
        assert "Gaddock Teeg" in names(svc, 'o:"can\u2019t be cast"')

    def test_order_and_direction(self, svc: SearchService) -> None:
        cards = svc.search("t:creature order:cmc direction:desc", limit=500)
        cmcs = [c.cmc for c in cards]
        assert cmcs == sorted(cmcs, reverse=True)
        cards = svc.search("t:creature order:power", limit=500)
        powers = [float(c.power) for c in cards if c.power not in (None, "*")]
        assert powers == sorted(powers)

    def test_split_mana_search_sees_second_half(self, svc: SearchService) -> None:
        # Was: only the left half's cost was stored.
        assert "Commit // Memory" in names(svc, "m:{w}{w}")
        assert "Wear // Tear" in names(svc, "m:w t:instant")

    def test_results_carry_full_split_cost(self, svc: SearchService) -> None:
        card = svc.search("!\"Fire // Ice\"")[0]
        assert card.mana_cost == "{1}{R} // {1}{U}"

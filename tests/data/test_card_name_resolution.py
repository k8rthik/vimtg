"""One card-name resolver: full names, face names, "Fire/Ice", accents.

Every lookup (get_by_name, get_by_names, and everything built on them)
must resolve the spellings other tools use for multi-face cards.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.domain.card import Card, Color
from vimtg.services.search_service import SearchService

FABLE = "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"
VALAKUT = "Valakut Awakening // Valakut Stoneforge"


@pytest.mark.parametrize(
    ("typed", "canonical"),
    [
        ("Fable of the Mirror-Breaker", FABLE),
        ("fable of the mirror-breaker", FABLE),
        ("Reflection of Kiki-Jiki", FABLE),
        (FABLE, FABLE),
        ("Bonecrusher Giant", "Bonecrusher Giant // Stomp"),
        ("Stomp", "Bonecrusher Giant // Stomp"),
        ("Fire/Ice", "Fire // Ice"),
        ("Fire // Ice", "Fire // Ice"),
        ("fire//ice", "Fire // Ice"),
        ("Fire", "Fire // Ice"),
        ("Ice", "Fire // Ice"),
        ("Valakut Awakening", VALAKUT),
        ("Valakut Stoneforge", VALAKUT),
        ("Emeria’s Call", "Emeria's Call // Emeria, Shattered Skyclave"),
        ("Delver of Secrets", "Delver of Secrets // Insectile Aberration"),
        ("Lim-Dul's Vault", "Lim-Dûl's Vault"),
        ("Æther Vial", "Aether Vial"),
        ("LIGHTNING BOLT", "Lightning Bolt"),
    ],
)
def test_get_by_name_and_get_by_names_agree(
    real_shape_repo: CardRepository, typed: str, canonical: str
) -> None:
    single = real_shape_repo.get_by_name(typed)
    assert single is not None, typed
    assert single.name == canonical
    batch = real_shape_repo.get_by_names([typed])
    found = batch.get(typed)
    assert found is not None
    assert found.scryfall_id == single.scryfall_id
    # The canonical full name resolves from the same map too
    assert batch.get(canonical) is found


def test_unknown_name_is_none(real_shape_repo: CardRepository) -> None:
    assert real_shape_repo.get_by_name("Not A Card") is None
    assert real_shape_repo.get_by_names(["Not A Card"]) == {}
    assert real_shape_repo.get_by_names([]) == {}


def test_full_name_beats_another_cards_face(
    real_shape_repo: CardRepository, real_shape_cards: list[dict[str, Any]]
) -> None:
    """A real card literally named 'Fire' must not be shadowed by the
    'Fire' half of Fire // Ice (and vice versa the split still resolves)."""
    bolt = next(d for d in real_shape_cards if d["name"] == "Lightning Bolt")
    fire = {**bolt, "id": "fire-id", "oracle_id": "fire-oracle", "name": "Fire"}
    real_shape_repo.bulk_insert([Card.from_scryfall(fire)])
    got = real_shape_repo.get_by_name("Fire")
    assert got is not None and got.name == "Fire"
    assert real_shape_repo.get_by_names(["fire"]).get("Fire") == got
    split = real_shape_repo.get_by_name("Fire/Ice")
    assert split is not None and split.name == "Fire // Ice"


def test_many_names_batch(real_shape_repo: CardRepository) -> None:
    names = ["Stomp", "Fire/Ice", "sol ring", "Valakut Awakening", "Missing"]
    found = real_shape_repo.get_by_names(names)
    for name in names[:-1]:
        assert name in found
    assert "Missing" not in found


class TestSearchFindsFaceColoredCards:
    def test_color_filter_finds_dfcs(self, real_shape_repo: CardRepository) -> None:
        results = SearchService(real_shape_repo).search("c:r", limit=100)
        names = {c.name for c in results}
        assert FABLE in names
        assert VALAKUT in names
        assert "Delver of Secrets // Insectile Aberration" not in names

    def test_ligature_search(self, real_shape_repo: CardRepository) -> None:
        assert [c.name for c in real_shape_repo.search("Æther Vial")] == ["Aether Vial"]

    def test_slash_search(self, real_shape_repo: CardRepository) -> None:
        assert "Fire // Ice" in [c.name for c in real_shape_repo.search("Fire/Ice")]


class TestStaleRows:
    """Re-syncing after Scryfall changes a card's representative printing
    must not leave the old printing behind."""

    def _reprinted(self, card: Card, legal: str) -> Card:
        return dataclasses.replace(
            card,
            scryfall_id=card.scryfall_id + "-new",
            set_code="new",
            legalities={**card.legalities, "modern": legal},
        )

    def test_replace_all_drops_old_printing(
        self, real_shape_repo: CardRepository, real_shape_cards: list[dict[str, Any]]
    ) -> None:
        cards = [Card.from_scryfall(d) for d in real_shape_cards]
        before = real_shape_repo.count()
        updated = [
            self._reprinted(c, "banned") if c.name == "Lightning Bolt" else c for c in cards
        ]
        real_shape_repo.replace_all(updated)

        assert real_shape_repo.count() == before
        assert [c.set_code for c in real_shape_repo.search("Lightning Bolt")] == ["new"]
        single = real_shape_repo.get_by_name("Lightning Bolt")
        batch = real_shape_repo.get_by_names(["Lightning Bolt"])["Lightning Bolt"]
        assert single is not None
        assert single.legalities["modern"] == batch.legalities["modern"] == "banned"

    def test_replace_all_drops_cards_no_longer_in_feed(
        self, real_shape_repo: CardRepository, real_shape_cards: list[dict[str, Any]]
    ) -> None:
        cards = [Card.from_scryfall(d) for d in real_shape_cards if d["name"] != "Sol Ring"]
        real_shape_repo.replace_all(cards)
        assert real_shape_repo.get_by_name("Sol Ring") is None
        assert real_shape_repo.search("Sol Ring") == []

    def test_bulk_insert_supersedes_same_oracle_id(
        self, real_shape_repo: CardRepository, real_shape_cards: list[dict[str, Any]]
    ) -> None:
        bolt = Card.from_scryfall(
            next(d for d in real_shape_cards if d["name"] == "Lightning Bolt")
        )
        before = real_shape_repo.count()
        real_shape_repo.bulk_insert([self._reprinted(bolt, "banned")])
        assert real_shape_repo.count() == before
        assert len(real_shape_repo.search("Lightning Bolt")) == 1
        got = real_shape_repo.get_by_name("Lightning Bolt")
        assert got is not None and got.set_code == "new"

    def test_replace_all_is_atomic(
        self, real_shape_repo: CardRepository, real_shape_cards: list[dict[str, Any]]
    ) -> None:
        """A sync that dies mid-load keeps the previous card set intact."""
        before = real_shape_repo.count()

        def exploding() -> Any:
            yield Card.from_scryfall(real_shape_cards[0])
            raise RuntimeError("feed died")

        with pytest.raises(RuntimeError):
            real_shape_repo.replace_all(exploding(), synced_at="2030-01-01T00:00:00+00:00")
        assert real_shape_repo.count() == before
        assert real_shape_repo.get_by_name("Stomp") is not None
        assert real_shape_repo.get_last_sync() != "2030-01-01T00:00:00+00:00"

    def test_replace_all_records_sync_date_and_keeps_other_tables(
        self, db_factory: Callable[..., Database], real_shape_cards: list[dict[str, Any]]
    ) -> None:
        db = db_factory()
        conn = db.connect()
        conn.execute(
            "INSERT INTO snapshots (id, deck_path, deck_state, timestamp) "
            "VALUES ('s1', '/d.deck', '4 Lightning Bolt', '2026-01-01')"
        )
        conn.commit()
        repo = CardRepository(db)
        cards = [Card.from_scryfall(d) for d in real_shape_cards]
        repo.replace_all(cards, synced_at="2026-10-10T00:00:00+00:00")
        repo.replace_all(cards, synced_at="2026-10-11T00:00:00+00:00")
        assert repo.get_last_sync() == "2026-10-11T00:00:00+00:00"
        assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1


def test_round_trip_new_columns(real_shape_repo: CardRepository) -> None:
    sol_ring = real_shape_repo.get_by_name("Sol Ring")
    assert sol_ring is not None
    assert sol_ring.produced_mana == ("C",)
    assert sol_ring.game_changer is True
    assert sol_ring.oracle_id is not None
    valakut = real_shape_repo.get_by_name("Valakut Awakening")
    assert valakut is not None
    assert valakut.produced_mana == ("R",)
    assert valakut.colors == (Color.RED,)
    assert valakut.game_changer is False

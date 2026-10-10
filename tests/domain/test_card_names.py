"""Card-name normalisation and the normalising CardMap."""

from __future__ import annotations

from typing import Any

import pytest

from vimtg.domain.card import Card
from vimtg.domain.card_names import (
    RANK_FRONT_FACE,
    RANK_FULL_NAME,
    RANK_OTHER_FACE,
    CardMap,
    face_names,
    name_aliases,
    normalize_card_name,
)


def _card(real_shape_cards: list[dict[str, Any]], name: str) -> Card:
    return Card.from_scryfall(next(d for d in real_shape_cards if d["name"] == name))


class TestNormalizeCardName:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("Lightning Bolt", "lightning bolt"),
            ("LIGHTNING  BOLT ", "Lightning Bolt"),
            ("Fire // Ice", "Fire/Ice"),
            ("Fire // Ice", "fire//ice"),
            ("Fire // Ice", "Fire / Ice"),
            ("Lim-Dûl's Vault", "Lim-Dul's Vault"),
            ("Aether Vial", "Æther Vial"),
            ("Emeria's Call", "Emeria’s Call"),
            ("Jötun Grunt", "Jotun Grunt"),
        ],
    )
    def test_equivalent_spellings_share_a_key(self, a: str, b: str) -> None:
        assert normalize_card_name(a) == normalize_card_name(b)

    def test_separator_is_canonical(self) -> None:
        assert normalize_card_name("Fire/Ice") == "fire // ice"

    def test_distinct_cards_stay_distinct(self) -> None:
        assert normalize_card_name("Fire") != normalize_card_name("Fire // Ice")


class TestAliases:
    def test_single_faced_card_has_only_its_name(self) -> None:
        assert face_names("Lightning Bolt") == ("Lightning Bolt",)
        assert name_aliases("Lightning Bolt") == [("lightning bolt", RANK_FULL_NAME)]

    def test_multi_face_card_resolves_under_every_face(self) -> None:
        aliases = name_aliases("Fable of the Mirror-Breaker // Reflection of Kiki-Jiki")
        assert aliases == [
            ("fable of the mirror-breaker // reflection of kiki-jiki", RANK_FULL_NAME),
            ("fable of the mirror-breaker", RANK_FRONT_FACE),
            ("reflection of kiki-jiki", RANK_OTHER_FACE),
        ]

    def test_five_face_split(self) -> None:
        faces = face_names("Who // What // When // Where // Why")
        assert faces == ("Who", "What", "When", "Where", "Why")
        assert len(name_aliases("Who // What // When // Where // Why")) == 6


class TestCardMap:
    def test_lookup_with_any_spelling(self, real_shape_cards: list[dict[str, Any]]) -> None:
        fire_ice = _card(real_shape_cards, "Fire // Ice")
        cards = CardMap({"Fire // Ice": fire_ice})
        assert cards.get("Fire/Ice") is fire_ice
        assert cards["fire // ice"] is fire_ice
        assert "FIRE/ICE" in cards
        assert "Fire" not in cards
        assert 42 not in cards
        assert cards.get("Lightning Bolt") is None

    def test_copy_update_and_setdefault_keep_normalising(
        self, real_shape_cards: list[dict[str, Any]]
    ) -> None:
        bolt = _card(real_shape_cards, "Lightning Bolt")
        vial = _card(real_shape_cards, "Aether Vial")
        cards = CardMap([("Lightning Bolt", bolt)])
        cards.update({"Æther Vial": vial})
        assert cards.setdefault("LIGHTNING BOLT", vial) is bolt
        copied = cards.copy()
        assert isinstance(copied, CardMap)
        assert copied.get("aether vial") is vial
        assert set(copied) == {"lightning bolt", "aether vial"}

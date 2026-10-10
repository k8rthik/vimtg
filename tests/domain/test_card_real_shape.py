"""Card.from_scryfall against real-shaped Scryfall entries.

Scryfall omits top-level ``colors``, ``mana_cost`` and ``image_uris`` on
transform and modal DFCs; they live on each face.
"""

from __future__ import annotations

from typing import Any

from vimtg.domain.card import Card, Color


def _card(real_shape_cards: list[dict[str, Any]], name: str) -> Card:
    return Card.from_scryfall(next(d for d in real_shape_cards if d["name"] == name))


class TestFaceColors:
    def test_transform_takes_colors_from_faces(
        self, real_shape_cards: list[dict[str, Any]]
    ) -> None:
        fable = _card(real_shape_cards, "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki")
        assert fable.colors == (Color.RED,)
        assert fable.mana_cost == "{2}{R}"
        assert fable.image_uri is not None and "fable" in fable.image_uri

        delver = _card(real_shape_cards, "Delver of Secrets // Insectile Aberration")
        assert delver.colors == (Color.BLUE,)

    def test_mdfc_with_colorless_land_back(
        self, real_shape_cards: list[dict[str, Any]]
    ) -> None:
        valakut = _card(real_shape_cards, "Valakut Awakening // Valakut Stoneforge")
        assert valakut.colors == (Color.RED,)
        assert valakut.mana_cost == "{2}{R}"
        emeria = _card(real_shape_cards, "Emeria's Call // Emeria, Shattered Skyclave")
        assert emeria.colors == (Color.WHITE,)

    def test_union_of_face_colors_in_wubrg_order(self) -> None:
        data = {
            "id": "x",
            "name": "A // B",
            "layout": "modal_dfc",
            "card_faces": [
                {"name": "A", "mana_cost": "{G}", "colors": ["G"]},
                {"name": "B", "mana_cost": "{W}", "colors": ["W"]},
            ],
        }
        assert Card.from_scryfall(data).colors == (Color.WHITE, Color.GREEN)

    def test_top_level_colors_still_win(
        self, real_shape_cards: list[dict[str, Any]]
    ) -> None:
        fire_ice = _card(real_shape_cards, "Fire // Ice")
        assert fire_ice.colors == (Color.RED, Color.BLUE)
        assert _card(real_shape_cards, "Sol Ring").colors == ()

    def test_faced_layout_without_top_level_cost_reads_front_face(self) -> None:
        data = {
            "id": "x",
            "name": "Front // Back",
            "layout": "reversible_card",
            "card_faces": [
                {"name": "Front", "mana_cost": "{1}{B}", "colors": ["B"],
                 "oracle_id": "oid-front", "oracle_text": "Front text."},
                {"name": "Back", "mana_cost": "{1}{B}", "colors": ["B"]},
            ],
        }
        card = Card.from_scryfall(data)
        assert card.mana_cost == "{1}{B}"
        assert card.oracle_text == "Front text."
        assert card.colors == (Color.BLACK,)
        assert card.oracle_id == "oid-front"


class TestNewFields:
    def test_produced_mana_and_game_changer(
        self, real_shape_cards: list[dict[str, Any]]
    ) -> None:
        sol_ring = _card(real_shape_cards, "Sol Ring")
        assert sol_ring.produced_mana == ("C",)
        assert sol_ring.game_changer is True
        valakut = _card(real_shape_cards, "Valakut Awakening // Valakut Stoneforge")
        assert valakut.produced_mana == ("R",)
        assert valakut.game_changer is False

    def test_oracle_id(self, real_shape_cards: list[dict[str, Any]]) -> None:
        bolt_data = next(d for d in real_shape_cards if d["name"] == "Lightning Bolt")
        assert Card.from_scryfall(bolt_data).oracle_id == bolt_data["oracle_id"]

    def test_missing_fields_default(self) -> None:
        card = Card.from_scryfall({"id": "x", "name": "Plain"})
        assert card.produced_mana == ()
        assert card.game_changer is False
        assert card.oracle_id is None

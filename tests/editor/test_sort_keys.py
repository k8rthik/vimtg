"""Tests for the shared sort-key extraction module."""

from __future__ import annotations

from vimtg.domain.card import Card
from vimtg.editor.buffer import Buffer
from vimtg.editor.sort_keys import (
    CARD_DATA_FIELDS,
    SORT_FIELDS,
    extract_card_name,
    extract_sort_key,
    stat_to_float,
)


def _card(
    name: str,
    power: str | None = None,
    toughness: str | None = None,
    rarity: str = "common",
    cmc: float = 1.0,
    prices: dict[str, str] | None = None,
) -> Card:
    return Card.from_scryfall({
        "id": "x",
        "name": name,
        "cmc": cmc,
        "type_line": "Creature",
        "power": power,
        "toughness": toughness,
        "rarity": rarity,
        "prices": prices or {},
    })


def _line(text: str):  # type: ignore[no-untyped-def]
    return Buffer.from_text(text + "\n").get_line(0)


class TestStatToFloat:
    def test_plain_number(self) -> None:
        assert stat_to_float("3") == 3.0

    def test_star_is_zero(self) -> None:
        assert stat_to_float("*") == 0.0

    def test_hybrid(self) -> None:
        assert stat_to_float("1+*") == 1.0

    def test_none(self) -> None:
        assert stat_to_float(None) is None

    def test_empty(self) -> None:
        assert stat_to_float("") is None

    def test_negative(self) -> None:
        assert stat_to_float("-1") == -1.0


class TestNewFields:
    def test_power_sorts_numerically(self) -> None:
        resolved = {
            "Big": _card("Big", power="8", toughness="8"),
            "Small": _card("Small", power="1", toughness="1"),
        }
        big = extract_sort_key(_line("1 Big"), "power", resolved)
        small = extract_sort_key(_line("1 Small"), "power", resolved)
        assert small < big

    def test_missing_power_sorts_last(self) -> None:
        resolved = {"Spell": _card("Spell"), "Bear": _card("Bear", power="2")}
        spell = extract_sort_key(_line("1 Spell"), "power", resolved)
        bear = extract_sort_key(_line("1 Bear"), "power", resolved)
        assert bear < spell

    def test_rarity_order(self) -> None:
        resolved = {
            "C": _card("C", rarity="common"),
            "M": _card("M", rarity="mythic"),
        }
        common = extract_sort_key(_line("1 C"), "rarity", resolved)
        mythic = extract_sort_key(_line("1 M"), "rarity", resolved)
        assert common < mythic

    def test_price_uses_source(self) -> None:
        resolved = {
            "Cheap": _card("Cheap", prices={"usd": "0.10", "eur": "9.00"}),
            "Dear": _card("Dear", prices={"usd": "5.00", "eur": "0.10"}),
        }
        cheap_usd = extract_sort_key(_line("1 Cheap"), "price", resolved)
        dear_usd = extract_sort_key(_line("1 Dear"), "price", resolved)
        assert cheap_usd < dear_usd
        cheap_eur = extract_sort_key(
            _line("1 Cheap"), "price", resolved, price_source="eur"
        )
        dear_eur = extract_sort_key(
            _line("1 Dear"), "price", resolved, price_source="eur"
        )
        assert dear_eur < cheap_eur

    def test_category_field_groups_alphabetically(self) -> None:
        draw = extract_sort_key(_line("1 Opt  @draw"), "category")
        ramp = extract_sort_key(_line("1 Cultivate  @ramp"), "category")
        none = extract_sort_key(_line("1 Shock"), "category")
        assert draw < ramp < none


class TestFieldSets:
    def test_card_data_fields_subset(self) -> None:
        assert CARD_DATA_FIELDS <= SORT_FIELDS

    def test_text_fields_do_not_need_card_data(self) -> None:
        for field in ("name", "qty", "tag", "category"):
            assert field in SORT_FIELDS
            assert field not in CARD_DATA_FIELDS


class TestExtractCardName:
    def test_strips_all_suffix_tokens(self) -> None:
        assert (
            extract_card_name("4 Cultivate  @ramp  #core  // note")
            == "Cultivate"
        )

    def test_sideboard_prefix(self) -> None:
        assert extract_card_name("SB: 2 Rest in Peace") == "Rest in Peace"

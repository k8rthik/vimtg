"""Collection CSV parsing and deck ownership: what a user owns versus
what the deck needs, and what finishing it costs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vimtg.data.deck_repository import parse_deck_text
from vimtg.domain.card import Card
from vimtg.domain.collection import (
    CollectionError,
    missing_list,
    ownership,
    parse_collection_csv,
    summarize_ownership,
)

SOURCE = Path("/home/me/manabox.csv")


@pytest.fixture
def cards() -> dict[str, Card]:
    path = Path(__file__).parent.parent / "fixtures" / "scryfall_sample.json"
    return {c["name"]: Card.from_scryfall(c) for c in json.loads(path.read_text())}


class TestParseCollectionCsv:
    def test_manabox_headers_sum_printings(self) -> None:
        text = (
            "Name,Set code,Set name,Collector number,Foil,Rarity,Quantity,"
            "ManaBox ID,Scryfall ID,Purchase price,Misprint,Altered,Condition,"
            "Language,Purchase price currency\n"
            "Lightning Bolt,sta,Strixhaven Mystical Archive,42,normal,rare,2,"
            "1,abc,1.00,false,false,near_mint,en,USD\n"
            "Lightning Bolt,m11,Magic 2011,149,foil,common,1,"
            "2,def,2.00,false,false,near_mint,en,USD\n"
            "Goblin Guide,zen,Zendikar,126,normal,rare,4,3,ghi,,false,false,"
            "near_mint,en,USD\n"
        )
        collection = parse_collection_csv(text, SOURCE)
        assert collection.owned_count("Lightning Bolt") == 3
        assert collection.owned_count("goblin guide") == 4
        assert collection.owned_count("Lava Spike") == 0
        assert collection.total_cards == 7
        assert collection.unique_cards == 2
        assert collection.skipped_rows == 0
        assert collection.source == SOURCE

    def test_moxfield_headers(self) -> None:
        text = (
            "Count,Tradelist Count,Name,Edition,Condition,Language,Foil,Tags,"
            "Last Modified,Collector Number\n"
            '4,0,Lightning Bolt,sta,Near Mint,English,,,"2024-01-01 10:00:00",42\n'
        )
        assert parse_collection_csv(text, SOURCE).owned_count("Lightning Bolt") == 4

    def test_archidekt_headers(self) -> None:
        text = (
            "Quantity,Name,Finish,Condition,Date Added,Language,Purchase Price,"
            "Tags,Edition Name,Edition Code,Multiverse Id,Scryfall ID,MTGO ID,"
            "Collector Number\n"
            "3,Lightning Bolt,Normal,NM,2024-01-01,EN,,,"
            "Strixhaven Mystical Archive,sta,,abc,,42\n"
        )
        assert parse_collection_csv(text, SOURCE).owned_count("Lightning Bolt") == 3

    def test_deckbox_headers(self) -> None:
        text = (
            "Count,Tradelist Count,Name,Edition,Card Number,Condition,Language,"
            "Foil,Signed,Artist Proof,Altered Art,Misprint,Promo,Textless,My Price\n"
            "2,0,Lightning Bolt,Strixhaven Mystical Archive,42,Near Mint,English,"
            ",,,,,,,\n"
        )
        assert parse_collection_csv(text, SOURCE).owned_count("Lightning Bolt") == 2

    def test_headers_match_case_insensitively_and_strip_printing_suffix(self) -> None:
        text = "quantity,NAME\n1,Goblin Guide (ZEN) 126 *F*\n"
        assert parse_collection_csv(text, SOURCE).owned_count("Goblin Guide") == 1

    def test_bom_and_crlf(self) -> None:
        text = "﻿Count,Name\r\n2,Lightning Bolt\r\n"
        assert parse_collection_csv(text, SOURCE).owned_count("Lightning Bolt") == 2

    def test_double_faced_names_match_the_front_face_both_ways(self) -> None:
        text = (
            "Count,Name\n"
            "1,Delver of Secrets // Insectile Aberration\n"
            "2,Bonecrusher Giant\n"
            "1,Fire // Ice\n"
        )
        collection = parse_collection_csv(text, SOURCE)
        assert collection.owned_count("Delver of Secrets") == 1
        assert collection.owned_count("Bonecrusher Giant // Stomp") == 2
        assert collection.owned_count("Fire/Ice") == 1
        assert collection.unique_cards == 3
        assert collection.total_cards == 4

    def test_rows_without_a_name_or_count_are_skipped_and_counted(self) -> None:
        text = (
            "Count,Name\n"
            "2,Lightning Bolt\n"
            ",Goblin Guide\n"
            "x,Lava Spike\n"
            "0,Mountain\n"
            "3,\n"
            ",,\n"
        )
        collection = parse_collection_csv(text, SOURCE)
        assert collection.owned_count("Lightning Bolt") == 2
        assert collection.total_cards == 2
        assert collection.skipped_rows == 4

    def test_unrecognisable_headers_name_what_was_found(self) -> None:
        with pytest.raises(CollectionError) as exc:
            parse_collection_csv("Card,Amount\nLightning Bolt,4\n", SOURCE)
        message = str(exc.value)
        assert "Card" in message and "Amount" in message
        assert "Name" in message and "Count" in message

    def test_empty_file_is_an_error(self) -> None:
        with pytest.raises(CollectionError):
            parse_collection_csv("", SOURCE)

    def test_status_line(self) -> None:
        collection = parse_collection_csv(
            "Count,Name\n4,Lightning Bolt\n2,Goblin Guide\nx,Mountain\n", SOURCE
        )
        assert collection.status() == (
            "Collection: 6 cards (2 unique) from manabox.csv, 1 row skipped"
        )


_DECK = (
    "// Deck: Burn\n"
    "4 Lightning Bolt\n"
    "4 Goblin Guide\n"
    "2 Lava Spike\n"
    "20 Mountain\n"
    "SB: 2 Lightning Bolt\n"
    "SB: 3 Rest in Peace\n"
    "MB: 1 Sacred Foundry\n"
)


def _collection(text: str):  # type: ignore[no-untyped-def]
    return parse_collection_csv(text, SOURCE)


class TestOwnership:
    def test_same_card_in_both_zones_shares_one_pool(self) -> None:
        collection = _collection(
            "Count,Name\n5,Lightning Bolt\n4,Goblin Guide\n20,Mountain\n"
        )
        owns = ownership(parse_deck_text(_DECK), collection)
        by_line = {(o.entry.card_name, o.entry.section.value): o for o in owns}
        main_bolt = by_line[("Lightning Bolt", "main")]
        side_bolt = by_line[("Lightning Bolt", "sideboard")]
        assert (main_bolt.needed, main_bolt.owned, main_bolt.missing) == (4, 4, 0)
        assert (side_bolt.needed, side_bolt.owned, side_bolt.missing) == (2, 1, 1)
        assert by_line[("Lava Spike", "main")].missing == 2
        assert by_line[("Goblin Guide", "main")].missing == 0
        assert ("Sacred Foundry", "maybeboard") not in by_line

    def test_summary_counts_and_cost_with_an_unpriced_card(
        self, cards: dict[str, Card]
    ) -> None:
        collection = _collection("Count,Name\n5,Lightning Bolt\n4,Goblin Guide\n")
        owns = ownership(parse_deck_text(_DECK), collection)
        summary = summarize_ownership(owns, cards, "usd")
        assert summary.needed_cards == 35
        assert summary.owned_cards == 9
        assert summary.missing_cards == 26
        assert summary.missing_unique == 4
        # 1 Bolt at 1.50, 2 Lava Spike at 0.50, 3 Rest in Peace at 4.00;
        # Mountain has no price
        assert summary.cost_to_complete == pytest.approx(14.50)
        assert summary.unpriced_unique == 1
        assert summary.price_source == "usd"

    def test_summary_cost_is_none_when_nothing_missing_is_priced(
        self, cards: dict[str, Card]
    ) -> None:
        collection = _collection(
            "Count,Name\n6,Lightning Bolt\n4,Goblin Guide\n2,Lava Spike\n"
            "3,Rest in Peace\n"
        )
        summary = summarize_ownership(
            ownership(parse_deck_text(_DECK), collection), cards, "usd"
        )
        assert summary.missing_cards == 20
        assert summary.cost_to_complete is None
        assert summary.unpriced_unique == 1

    def test_missing_list_mainboard_then_sideboard(self, cards: dict[str, Card]) -> None:
        collection = _collection("Count,Name\n5,lightning bolt\n20,Mountain\n")
        owns = ownership(parse_deck_text(_DECK), collection)
        assert missing_list(owns, cards) == (
            "4 Goblin Guide\n"
            "2 Lava Spike\n"
            "\n"
            "1 Lightning Bolt\n"
            "3 Rest in Peace\n"
        )

    def test_missing_list_merges_duplicate_lines_and_skips_empty_blocks(
        self, cards: dict[str, Card]
    ) -> None:
        deck = parse_deck_text("2 Lightning Bolt\n// Burn\n2 Lightning Bolt\n")
        owns = ownership(deck, _collection("Count,Name\n1,Lightning Bolt\n"))
        assert missing_list(owns, cards) == "3 Lightning Bolt\n"

    def test_missing_list_is_empty_when_everything_is_owned(
        self, cards: dict[str, Card]
    ) -> None:
        deck = parse_deck_text("2 Lightning Bolt\n")
        owns = ownership(deck, _collection("Count,Name\n2,Lightning Bolt\n"))
        assert missing_list(owns, cards) == ""

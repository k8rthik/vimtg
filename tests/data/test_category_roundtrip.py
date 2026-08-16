"""Category round-trip through the deck parser and serializer."""

from __future__ import annotations

from vimtg.data.deck_repository import parse_deck_text, serialize_deck


class TestCategoryRoundtrip:
    def test_parse_reads_category(self) -> None:
        deck = parse_deck_text("4 Cultivate  @ramp  #core  // note\n")
        entry = deck.entries[0]
        assert entry.card_name == "Cultivate"
        assert entry.category == "ramp"
        assert entry.tags == frozenset({"core"})
        assert entry.comment == "note"

    def test_serialize_writes_canonical_order(self) -> None:
        deck = parse_deck_text("4 Cultivate  #core  @ramp\n")
        out = serialize_deck(deck)
        assert "4 Cultivate  @ramp  #core" in out

    def test_roundtrip_preserves_category(self) -> None:
        text = "SB: 2 Rest in Peace  @graveyard-hate\n"
        deck = parse_deck_text(text)
        assert deck.entries[0].category == "graveyard-hate"
        reparsed = parse_deck_text(serialize_deck(deck))
        assert reparsed.entries[0].category == "graveyard-hate"

    def test_no_category_stays_absent(self) -> None:
        deck = parse_deck_text("4 Cultivate\n")
        assert deck.entries[0].category == ""
        assert "@" not in serialize_deck(deck)

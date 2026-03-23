"""Tests for the Deck domain model."""

from vimtg.domain.deck import (
    CommentLine,
    Deck,
    DeckEntry,
    DeckMetadata,
    DeckSection,
)


def _make_deck(
    entries: tuple[DeckEntry, ...] = (),
    metadata: DeckMetadata | None = None,
    comments: tuple[CommentLine, ...] = (),
) -> Deck:
    return Deck(
        metadata=metadata or DeckMetadata(),
        entries=entries,
        comments=comments,
    )


def _entry(
    qty: int, name: str, section: DeckSection = DeckSection.MAIN
) -> DeckEntry:
    return DeckEntry(quantity=qty, card_name=name, section=section)


class TestDeckTotalCards:
    def test_deck_total_cards(self) -> None:
        deck = _make_deck(
            entries=(
                _entry(4, "Lightning Bolt"),
                _entry(4, "Goblin Guide"),
                _entry(4, "Lava Spike"),
            )
        )
        assert deck.total_cards() == 12

    def test_empty_deck_total_cards(self) -> None:
        deck = _make_deck()
        assert deck.total_cards() == 0


class TestDeckFilters:
    def test_deck_mainboard_filter(self) -> None:
        entries = (
            _entry(4, "Lightning Bolt", DeckSection.MAIN),
            _entry(2, "Rest in Peace", DeckSection.SIDEBOARD),
            _entry(3, "Goblin Guide", DeckSection.MAIN),
        )
        deck = _make_deck(entries=entries)
        mainboard = deck.mainboard()
        assert len(mainboard) == 2
        assert all(e.section == DeckSection.MAIN for e in mainboard)

    def test_deck_sideboard_filter(self) -> None:
        entries = (
            _entry(4, "Lightning Bolt", DeckSection.MAIN),
            _entry(2, "Rest in Peace", DeckSection.SIDEBOARD),
            _entry(3, "Kor Firewalker", DeckSection.SIDEBOARD),
        )
        deck = _make_deck(entries=entries)
        sideboard = deck.sideboard()
        assert len(sideboard) == 2
        assert all(e.section == DeckSection.SIDEBOARD for e in sideboard)

    def test_deck_unique_names(self) -> None:
        entries = (
            _entry(4, "Lightning Bolt", DeckSection.MAIN),
            _entry(2, "Lightning Bolt", DeckSection.SIDEBOARD),
            _entry(3, "Goblin Guide", DeckSection.MAIN),
        )
        deck = _make_deck(entries=entries)
        names = deck.unique_card_names()
        assert names == frozenset({"Lightning Bolt", "Goblin Guide"})


class TestAddEntry:
    def test_add_entry_new(self) -> None:
        deck = _make_deck(entries=(_entry(4, "Lightning Bolt"),))
        new_entry = _entry(3, "Goblin Guide")
        updated = deck.add_entry(new_entry)
        assert len(updated.entries) == 2
        assert updated.total_cards() == 7

    def test_add_entry_existing(self) -> None:
        deck = _make_deck(entries=(_entry(4, "Lightning Bolt"),))
        new_entry = _entry(2, "Lightning Bolt")
        updated = deck.add_entry(new_entry)
        assert len(updated.entries) == 1
        assert updated.entries[0].quantity == 6

    def test_add_entry_immutable(self) -> None:
        original_entries = (_entry(4, "Lightning Bolt"),)
        deck = _make_deck(entries=original_entries)
        new_entry = _entry(2, "Lightning Bolt")
        updated = deck.add_entry(new_entry)
        # Original deck unchanged
        assert deck.entries[0].quantity == 4
        assert deck is not updated
        assert updated.entries[0].quantity == 6

    def test_add_entry_same_card_different_section(self) -> None:
        deck = _make_deck(
            entries=(_entry(4, "Lightning Bolt", DeckSection.MAIN),)
        )
        sb_entry = _entry(2, "Lightning Bolt", DeckSection.SIDEBOARD)
        updated = deck.add_entry(sb_entry)
        assert len(updated.entries) == 2
        assert updated.total_cards() == 6


class TestRemoveEntry:
    def test_remove_entry(self) -> None:
        entries = (
            _entry(4, "Lightning Bolt"),
            _entry(3, "Goblin Guide"),
        )
        deck = _make_deck(entries=entries)
        updated = deck.remove_entry("Lightning Bolt", DeckSection.MAIN)
        assert len(updated.entries) == 1
        assert updated.entries[0].card_name == "Goblin Guide"

    def test_remove_entry_not_found(self) -> None:
        entries = (
            _entry(4, "Lightning Bolt"),
            _entry(3, "Goblin Guide"),
        )
        deck = _make_deck(entries=entries)
        updated = deck.remove_entry("Lava Spike", DeckSection.MAIN)
        assert len(updated.entries) == 2


class TestUpdateQuantity:
    def test_update_quantity(self) -> None:
        deck = _make_deck(entries=(_entry(4, "Lightning Bolt"),))
        updated = deck.update_quantity(
            "Lightning Bolt", DeckSection.MAIN, 2
        )
        assert updated.entries[0].quantity == 2

    def test_update_quantity_zero_removes(self) -> None:
        entries = (
            _entry(4, "Lightning Bolt"),
            _entry(3, "Goblin Guide"),
        )
        deck = _make_deck(entries=entries)
        updated = deck.update_quantity(
            "Lightning Bolt", DeckSection.MAIN, 0
        )
        assert len(updated.entries) == 1
        assert updated.entries[0].card_name == "Goblin Guide"

    def test_update_quantity_negative_removes(self) -> None:
        deck = _make_deck(entries=(_entry(4, "Lightning Bolt"),))
        updated = deck.update_quantity(
            "Lightning Bolt", DeckSection.MAIN, -1
        )
        assert len(updated.entries) == 0

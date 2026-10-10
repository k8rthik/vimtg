"""Merging a pasted decklist into the buffer (normal-mode paste)."""

from __future__ import annotations

from vimtg.domain.deck import Deck, DeckEntry, DeckMetadata, DeckSection
from vimtg.editor.buffer import Buffer
from vimtg.editor.paste_deck import add_deck_entries


def _deck(*entries: DeckEntry) -> Deck:
    return Deck(metadata=DeckMetadata(), entries=tuple(entries), comments=())


def _e(qty: int, name: str, section: DeckSection = DeckSection.MAIN) -> DeckEntry:
    return DeckEntry(quantity=qty, card_name=name, section=section)


BASE = "// Deck: Burn\n\n4 Lightning Bolt\n\nSB: 2 Smash to Smithereens\n"


def test_existing_card_gains_copies_in_its_zone() -> None:
    result = add_deck_entries(
        Buffer.from_text(BASE), _deck(_e(2, "lightning bolt")), auto_sort=False
    )
    text = result.buffer.to_text()
    assert "6 Lightning Bolt" in text
    assert result.cards == 2
    assert result.buffer.card_name_at(result.first_row or 0) == "Lightning Bolt"


def test_same_name_in_other_zone_is_separate() -> None:
    result = add_deck_entries(
        Buffer.from_text(BASE),
        _deck(_e(1, "Lightning Bolt", DeckSection.SIDEBOARD)),
        auto_sort=False,
    )
    text = result.buffer.to_text()
    assert "4 Lightning Bolt" in text
    assert "1 Lightning Bolt" in text  # sideboard copy, not merged into main


def test_new_cards_land_in_their_zones() -> None:
    result = add_deck_entries(
        Buffer.from_text(BASE),
        _deck(
            _e(4, "Monastery Swiftspear"),
            _e(1, "Pyroblast", DeckSection.SIDEBOARD),
            _e(1, "Kediss, Emberclaw Familiar", DeckSection.COMMANDER),
        ),
        auto_sort=False,
    )
    buf = result.buffer
    rows = {buf.card_name_at(i): buf.get_line(i).line_type.name for i in range(buf.line_count())}
    assert rows["Monastery Swiftspear"] == "CARD_ENTRY"
    assert rows["Pyroblast"] == "SIDEBOARD_ENTRY"
    assert rows["Kediss, Emberclaw Familiar"] == "COMMANDER_ENTRY"
    assert result.cards == 6
    assert buf.card_name_at(result.first_row or 0) == "Monastery Swiftspear"


def test_auto_sort_files_by_type() -> None:
    types = {"Mountain": "Basic Land — Mountain", "Shock": "Instant"}
    result = add_deck_entries(
        Buffer.from_text("// Deck: x\n"),
        _deck(_e(20, "Mountain"), _e(4, "Shock")),
        auto_sort=True,
        type_line=types.get,
    )
    assert result.buffer.to_text() == (
        "// Deck: x\n\n// Lands\n20 Mountain\n\n// Instants\n4 Shock\n"
    )
    assert result.buffer.card_name_at(result.first_row or 0) == "Mountain"


def test_empty_deck_adds_nothing() -> None:
    buf = Buffer.from_text(BASE)
    result = add_deck_entries(buf, _deck(), auto_sort=False)
    assert result.buffer is buf
    assert result.first_row is None and result.cards == 0

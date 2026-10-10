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


def test_separator_spelling_merges_into_existing_line() -> None:
    # Regression: pasting "4 Fire/Ice" next to "Fire // Ice" added a
    # second line, so copies were counted by spelling
    base = "// Deck: Izzet\n\n4 Fire // Ice\n"
    result = add_deck_entries(
        Buffer.from_text(base), _deck(_e(4, "Fire/Ice")), auto_sort=False
    )
    lines = result.buffer.to_text().splitlines()
    assert "8 Fire // Ice" in lines
    assert sum("Fire" in line for line in lines) == 1


def test_card_key_merges_other_face_into_existing_line() -> None:
    # With card data the TUI keys cards by oracle id: a back-face name
    # joins the front-face line
    oracle = {"delver of secrets": "o1", "insectile aberration": "o1"}
    base = "// Deck: Delver\n\n4 Delver of Secrets\n"
    result = add_deck_entries(
        Buffer.from_text(base),
        _deck(_e(2, "Insectile Aberration")),
        auto_sort=False,
        card_key=lambda name: oracle.get(name.lower(), name.lower()),
    )
    lines = result.buffer.to_text().splitlines()
    assert "6 Delver of Secrets" in lines
    assert not any("Insectile" in line for line in lines)

"""DeckView renders header count annotations end-to-end."""

from vimtg.editor.buffer import Buffer
from vimtg.tui.widgets.deck_view import DeckView


def test_deck_view_annotates_headers() -> None:
    dv = DeckView()
    dv.buffer = Buffer.from_text(
        "// Deck: Test\n\n// Creatures\n4 Bear\n2 Wolf\n\n// Lands\n20 Forest\n"
    )
    out = dv.render().plain
    assert "26 cards" in out  # // Deck: line carries the deck total
    assert "(6)" in out       # Creatures section
    assert "(20)" in out      # Lands section


def test_deck_view_deck_line_splits_sideboard() -> None:
    dv = DeckView()
    dv.buffer = Buffer.from_text(
        "// Deck: Test\n\n4 Bear\n2 Wolf\n\nSB: 3 Duress\n"
    )
    out = dv.render().plain
    assert "6/3 cards" in out  # mainboard/sideboard split on // Deck:


def test_deck_view_counts_follow_edits() -> None:
    dv = DeckView()
    dv.buffer = Buffer.from_text("// Creatures\n4 Bear\n")
    assert "(4)" in dv.render().plain
    dv.buffer = dv.buffer.set_quantity(1, 3)
    assert "(3)" in dv.render().plain

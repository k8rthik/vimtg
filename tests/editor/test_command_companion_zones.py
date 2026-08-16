"""Commander/companion zones: parsing, moves (mc/mp), and placement."""

from __future__ import annotations

from vimtg.data.deck_repository import parse_deck_text, serialize_deck
from vimtg.domain.deck import DeckSection
from vimtg.editor.buffer import Buffer, LineType, classify_line
from vimtg.editor.cursor import Cursor
from vimtg.editor.keymap import KeyMap, KeyResult
from vimtg.editor.operators import move_to_zone


class TestCompanionLineGrammar:
    def test_cmp_line_classifies_as_companion(self):
        assert classify_line("CMP: 1 Lurrus of the Dream-Den") is (
            LineType.COMPANION_ENTRY
        )

    def test_companion_is_a_card_line(self):
        buf = Buffer.from_text("CMP: 1 Lurrus of the Dream-Den\n")
        assert buf.is_card_line(0)
        assert buf.card_name_at(0) == "Lurrus of the Dream-Den"
        assert buf.quantity_at(0) == 1

    def test_companion_quantity_edit_keeps_prefix(self):
        buf = Buffer.from_text("CMP: 1 Lurrus of the Dream-Den\n")
        buf = buf.set_quantity(0, 2)
        assert buf.get_line(0).text == "CMP: 2 Lurrus of the Dream-Den"

    def test_parse_and_serialize_roundtrip(self):
        text = "CMD: 1 Atraxa\n\nCMP: 1 Lurrus of the Dream-Den\n\n99 Forest\n"
        deck = parse_deck_text(text)
        assert deck.companions()[0].card_name == "Lurrus of the Dream-Den"
        assert deck.companions()[0].section == DeckSection.COMPANION
        out = serialize_deck(deck)
        assert "CMP: 1 Lurrus of the Dream-Den" in out
        # Canonical order: commander before companion before mainboard
        assert out.index("CMD:") < out.index("CMP:") < out.index("99 Forest")

    def test_companion_suffix_tokens_survive(self):
        text = "CMP: 1 Lurrus of the Dream-Den  #core  // recursion\n"
        deck = parse_deck_text(text)
        entry = deck.companions()[0]
        assert entry.tags == frozenset({"core"})
        assert entry.comment == "recursion"


class TestKeymapZoneMoves:
    def test_mc_and_mp_complete_as_specials(self):
        for sub in ("c", "p"):
            km = KeyMap()
            km.feed("m")
            result, action = km.feed(sub)
            assert result == KeyResult.COMPLETE
            assert action is not None
            assert action.action == f"m{sub}"
            assert action.action_type == "special"
            assert action.count == 0  # "no count" sentinel, like ms/mm/md

    def test_other_letters_still_set_marks(self):
        km = KeyMap()
        km.feed("m")
        result, action = km.feed("a")
        assert result == KeyResult.COMPLETE
        assert action is not None
        assert action.action == "ma"


class TestMoveToCommander:
    def test_move_converts_to_cmd_line(self):
        buf = Buffer.from_text("1 Atraxa\n1 Forest\n")
        result = move_to_zone(buf, Cursor(row=0), LineType.COMMANDER_ENTRY)
        assert result.moved
        text = result.buffer.to_text()
        assert "CMD: 1 Atraxa" in text
        assert "commander" in result.message

    def test_new_commander_block_lands_before_first_section(self):
        buf = Buffer.from_text(
            "// Deck: X\n\n// Creatures\n1 Atraxa\n1 Birds of Paradise\n"
        )
        result = move_to_zone(buf, Cursor(row=3), LineType.COMMANDER_ENTRY)
        lines = result.buffer.to_text().splitlines()
        cmd_row = lines.index("CMD: 1 Atraxa")
        header_row = lines.index("// Creatures")
        assert cmd_row < header_row  # before the block, not inside it

    def test_move_from_commander_back_to_main(self):
        buf = Buffer.from_text("CMD: 1 Atraxa\n1 Forest\n")
        result = move_to_zone(buf, Cursor(row=0), LineType.CARD_ENTRY)
        assert result.moved
        assert "CMD:" not in result.buffer.to_text()
        assert "1 Atraxa" in result.buffer.to_text()

    def test_already_in_commander_is_noop(self):
        buf = Buffer.from_text("CMD: 1 Atraxa\n")
        result = move_to_zone(buf, Cursor(row=0), LineType.COMMANDER_ENTRY)
        assert not result.moved
        assert "Already in commander" in result.message


class TestMoveToCompanion:
    def test_move_converts_to_cmp_line(self):
        buf = Buffer.from_text("1 Lurrus of the Dream-Den\n1 Forest\n")
        result = move_to_zone(buf, Cursor(row=0), LineType.COMPANION_ENTRY)
        assert result.moved
        assert "CMP: 1 Lurrus of the Dream-Den" in result.buffer.to_text()
        assert "companion" in result.message

    def test_companion_block_lands_after_commander(self):
        buf = Buffer.from_text("CMD: 1 Atraxa\n\n1 Lurrus\n1 Forest\n")
        result = move_to_zone(buf, Cursor(row=2), LineType.COMPANION_ENTRY)
        lines = [
            line for line in result.buffer.to_text().splitlines() if line
        ]
        assert lines.index("CMD: 1 Atraxa") < lines.index("CMP: 1 Lurrus")
        assert lines.index("CMP: 1 Lurrus") < lines.index("1 Forest")

    def test_count_splits_copies(self):
        buf = Buffer.from_text("4 Mishra's Bauble\n")
        result = move_to_zone(
            buf, Cursor(row=0), LineType.COMPANION_ENTRY, count=1
        )
        text = result.buffer.to_text()
        assert "3 Mishra's Bauble" in text
        assert "CMP: 1 Mishra's Bauble" in text

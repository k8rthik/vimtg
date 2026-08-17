"""insertion_zone — the zone a card added at the cursor should join."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer, LineType, insertion_zone

_BLOCK_DECK = (
    "// Format: commander\n"
    "\n"
    "CMD:\n"
    "    1 Atraxa\n"
    "\n"
    "DCK:\n"
    "    // Creature\n"
    "    1 Birds\n"
    "\n"
    "MB: 1 Opt\n"
)


def _zone(text: str, row: int) -> LineType:
    return insertion_zone(Buffer.from_text(text), row)


class TestBlockContext:
    def test_inside_cmd_block(self):
        buf = Buffer.from_text("CMD:\n    1 Atraxa\n\n1 Forest\n")
        # A blank opened right under the commander line
        buf = buf.insert_line(2, "")
        assert insertion_zone(buf, 2) is LineType.COMMANDER_ENTRY

    def test_right_under_bare_zone_header(self):
        buf = Buffer.from_text("SB:\n\n1 Forest\n")
        assert insertion_zone(buf, 1) is LineType.SIDEBOARD_ENTRY

    def test_dck_block_is_mainboard(self):
        buf = Buffer.from_text(_BLOCK_DECK).insert_line(8, "")
        assert insertion_zone(buf, 8) is LineType.CARD_ENTRY

    def test_after_block_ends_falls_to_neighbor(self):
        buf = Buffer.from_text(_BLOCK_DECK)
        # Row after the MB: prefix line at the very end
        row = buf.line_count()
        buf = buf.insert_line(row, "")
        assert insertion_zone(buf, row) is LineType.MAYBEBOARD_ENTRY


class TestPrefixNeighborhood:
    def test_below_sb_prefix_line(self):
        buf = Buffer.from_text("4 Bolt\n\nSB: 2 Duress\n\n")
        assert insertion_zone(buf, 3) is LineType.SIDEBOARD_ENTRY

    def test_comments_are_looked_through(self):
        buf = Buffer.from_text("SB: 2 Duress\n// wishboard notes\n\n")
        assert insertion_zone(buf, 2) is LineType.SIDEBOARD_ENTRY

    def test_below_labeled_zone_header(self):
        buf = Buffer.from_text("4 Bolt\n\n// Sideboard\n\n")
        assert insertion_zone(buf, 3) is LineType.SIDEBOARD_ENTRY


class TestMainboardFallbacks:
    def test_top_of_file(self):
        assert _zone("\n4 Bolt\n", 0) is LineType.CARD_ENTRY

    def test_below_metadata(self):
        assert _zone("// Deck: X\n\n", 1) is LineType.CARD_ENTRY

    def test_below_type_header(self):
        assert _zone("// Creatures\n\n4 Birds\n", 1) is LineType.CARD_ENTRY

    def test_below_category_header(self):
        assert _zone("// @ramp\n\n1 Cultivate\n", 1) is LineType.CARD_ENTRY

    def test_above_cmd_header_is_mainboard(self):
        # O on the CMD: header itself opens ABOVE the block — outside it
        buf = Buffer.from_text("// Deck: X\n\nCMD:\n    1 Atraxa\n")
        buf = buf.insert_line(2, "")
        assert insertion_zone(buf, 2) is LineType.CARD_ENTRY

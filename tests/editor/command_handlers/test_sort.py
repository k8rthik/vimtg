"""Tests for the :sort command handler."""

from __future__ import annotations

from vimtg.domain.card import Card, Color, Rarity
from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.sort import cmd_sort
from vimtg.editor.commands import CommandRange, EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _make_card(
    name: str,
    cmc: float = 0.0,
    type_line: str = "Instant",
    colors: tuple[Color, ...] = (),
) -> Card:
    return Card(
        scryfall_id="test",
        name=name,
        mana_cost="",
        cmc=cmc,
        type_line=type_line,
        oracle_text="",
        colors=colors,
        color_identity=(),
        power=None,
        toughness=None,
        set_code="tst",
        rarity=Rarity.COMMON,
        prices={},
        legalities={},
        image_uri=None,
        layout="normal",
        keywords=(),
    )


def _make_cmd(
    args: str = "",
    bang: bool = False,
    cmd_range: CommandRange | None = None,
) -> ParsedCommand:
    return ParsedCommand(name="sort", args=args, cmd_range=cmd_range, bang=bang)


def _line_texts(buffer: Buffer) -> list[str]:
    return [bl.text for bl in buffer.get_lines()]


class TestSortByName:
    def test_sort_by_name_alphabetical(self) -> None:
        text = "4 Lightning Bolt\n2 Counterspell\n1 Abrade\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = _make_cmd(cmd_range=CommandRange(start=0, end=2))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        names = _line_texts(new_buf)
        assert names == ["1 Abrade", "2 Counterspell", "4 Lightning Bolt"]
        assert "Sorted 3 cards by name" in ctx.message

    def test_sort_reverse(self) -> None:
        text = "1 Abrade\n2 Counterspell\n4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = _make_cmd(bang=True, cmd_range=CommandRange(start=0, end=2))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        names = _line_texts(new_buf)
        assert names == ["4 Lightning Bolt", "2 Counterspell", "1 Abrade"]


class TestSortPreservesComments:
    def test_sort_preserves_comments(self) -> None:
        text = (
            "// Creature\n"
            "4 Lightning Bolt\n"
            "2 Counterspell\n"
            "1 Abrade\n"
        )
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=1)
        ctx = EditorContext()
        # Range covers the whole block including comment
        cmd = _make_cmd(cmd_range=CommandRange(start=0, end=3))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        # Comment stays anchored at position 0
        assert lines[0] == "// Creature"
        # Cards sorted after comment
        assert lines[1] == "1 Abrade"
        assert lines[2] == "2 Counterspell"
        assert lines[3] == "4 Lightning Bolt"


class TestSortCurrentSection:
    def test_sort_current_section(self) -> None:
        text = (
            "// Creature\n"
            "4 Lightning Bolt\n"
            "2 Counterspell\n"
            "1 Abrade\n"
            "\n"
            "// Land\n"
            "4 Mountain\n"
        )
        buffer = Buffer.from_text(text)
        # Cursor on a card in the first section
        cursor = Cursor(row=2)
        ctx = EditorContext()
        cmd = _make_cmd()  # No range -> sort current section

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        # Only the first card block (rows 1-3) should be sorted
        assert lines[0] == "// Creature"
        assert lines[1] == "1 Abrade"
        assert lines[2] == "2 Counterspell"
        assert lines[3] == "4 Lightning Bolt"
        # Rest unchanged
        assert lines[4] == ""
        assert lines[5] == "// Land"
        assert lines[6] == "4 Mountain"


class TestSortRange:
    def test_sort_only_specified_range(self) -> None:
        text = (
            "4 Lightning Bolt\n"
            "2 Counterspell\n"
            "1 Abrade\n"
            "3 Swords to Plowshares\n"
        )
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        # Only sort lines 0-1
        cmd = _make_cmd(cmd_range=CommandRange(start=0, end=1))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        assert lines[0] == "2 Counterspell"
        assert lines[1] == "4 Lightning Bolt"
        # Lines outside range unchanged
        assert lines[2] == "1 Abrade"
        assert lines[3] == "3 Swords to Plowshares"


class TestSortByQty:
    def test_sort_by_qty(self) -> None:
        text = "4 Lightning Bolt\n1 Abrade\n2 Counterspell\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = _make_cmd(args="qty", cmd_range=CommandRange(start=0, end=2))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        assert lines == ["1 Abrade", "2 Counterspell", "4 Lightning Bolt"]

    def test_sort_by_qty_with_sideboard(self) -> None:
        text = "SB: 3 Mystical Dispute\nSB: 1 Aether Gust\nSB: 2 Negate\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = _make_cmd(args="qty", cmd_range=CommandRange(start=0, end=2))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        assert lines[0] == "SB: 1 Aether Gust"
        assert lines[1] == "SB: 2 Negate"
        assert lines[2] == "SB: 3 Mystical Dispute"


class TestSortEdgeCases:
    def test_sort_empty_section(self) -> None:
        text = "// Empty section\n\n// Another\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = _make_cmd()

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        assert "No card section to sort" in ctx.message
        assert ctx.error is True

    def test_sort_unknown_field(self) -> None:
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = _make_cmd(args="bogus")

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        assert "Unknown sort field" in ctx.message
        assert ctx.error is True

    def test_sort_cmc_falls_back_to_name(self) -> None:
        text = "4 Lightning Bolt\n1 Abrade\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = _make_cmd(args="cmc", cmd_range=CommandRange(start=0, end=1))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        # Falls back to name sort
        assert lines[0] == "1 Abrade"
        assert lines[1] == "4 Lightning Bolt"
        assert "by name" in ctx.message


class TestSortByCmc:
    def test_sort_by_cmc_with_resolved_cards(self) -> None:
        text = "4 Lightning Bolt\n2 Counterspell\n1 Abrade\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        resolved = {
            "Lightning Bolt": _make_card("Lightning Bolt", cmc=1.0),
            "Counterspell": _make_card("Counterspell", cmc=2.0),
            "Abrade": _make_card("Abrade", cmc=2.0),
        }
        ctx = EditorContext(resolved_cards=resolved)
        cmd = _make_cmd(args="cmc", cmd_range=CommandRange(start=0, end=2))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        assert lines[0] == "4 Lightning Bolt"  # CMC 1
        # CMC 2 cards sorted alphabetically
        assert lines[1] == "1 Abrade"
        assert lines[2] == "2 Counterspell"
        assert "by cmc" in ctx.message


    def test_sort_by_cmc_partial_resolution(self) -> None:
        """Unresolved cards sort to end, no TypeError."""
        text = "4 Lightning Bolt\n2 FakeCard\n1 Abrade\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        resolved = {
            "Lightning Bolt": _make_card("Lightning Bolt", cmc=1.0),
            "Abrade": _make_card("Abrade", cmc=2.0),
        }
        ctx = EditorContext(resolved_cards=resolved)
        cmd = _make_cmd(args="cmc", cmd_range=CommandRange(start=0, end=2))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        assert lines[0] == "4 Lightning Bolt"  # CMC 1
        assert lines[1] == "1 Abrade"  # CMC 2
        assert lines[2] == "2 FakeCard"  # Unresolved → end


class TestSortByType:
    def test_sort_by_type_with_resolved_cards(self) -> None:
        text = "4 Lightning Bolt\n2 Tarmogoyf\n1 Island\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        resolved = {
            "Lightning Bolt": _make_card("Lightning Bolt", type_line="Instant"),
            "Tarmogoyf": _make_card("Tarmogoyf", type_line="Creature — Lhurgoyf"),
            "Island": _make_card("Island", type_line="Basic Land — Island"),
        }
        ctx = EditorContext(resolved_cards=resolved)
        cmd = _make_cmd(args="type", cmd_range=CommandRange(start=0, end=2))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        assert lines[0] == "2 Tarmogoyf"  # Creature (0)
        assert lines[1] == "4 Lightning Bolt"  # Instant (2)
        assert lines[2] == "1 Island"  # Land (6)


class TestSortByColor:
    def test_sort_by_color_with_resolved_cards(self) -> None:
        text = "4 Lightning Bolt\n2 Counterspell\n1 Swords to Plowshares\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        resolved = {
            "Lightning Bolt": _make_card(
                "Lightning Bolt", colors=(Color.RED,)
            ),
            "Counterspell": _make_card(
                "Counterspell", colors=(Color.BLUE,)
            ),
            "Swords to Plowshares": _make_card(
                "Swords to Plowshares", colors=(Color.WHITE,)
            ),
        }
        ctx = EditorContext(resolved_cards=resolved)
        cmd = _make_cmd(args="color", cmd_range=CommandRange(start=0, end=2))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        # WUBRG order: W=0, U=1, R=3
        assert lines[0] == "1 Swords to Plowshares"  # White
        assert lines[1] == "2 Counterspell"  # Blue
        assert lines[2] == "4 Lightning Bolt"  # Red

    def test_multicolor_after_mono(self) -> None:
        text = "4 Lightning Bolt\n2 Teferi\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        resolved = {
            "Lightning Bolt": _make_card(
                "Lightning Bolt", colors=(Color.RED,)
            ),
            "Teferi": _make_card(
                "Teferi", colors=(Color.WHITE, Color.BLUE)
            ),
        }
        ctx = EditorContext(resolved_cards=resolved)
        cmd = _make_cmd(args="color", cmd_range=CommandRange(start=0, end=1))

        new_buf, _ = cmd_sort(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        # Mono before multi
        assert lines[0] == "4 Lightning Bolt"
        assert lines[1] == "2 Teferi"

"""Tests for the :s substitute and :filter command handlers."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.substitute import cmd_filter_view, cmd_substitute
from vimtg.editor.commands import CommandRange, EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _make_cmd(
    args: str = "",
    cmd_range: CommandRange | None = None,
) -> ParsedCommand:
    return ParsedCommand(name="s", args=args, cmd_range=cmd_range)


def _line_texts(buffer: Buffer) -> list[str]:
    return [bl.text for bl in buffer.get_lines()]


class TestSubCurrentLine:
    def test_sub_current_line(self) -> None:
        """:s/Bolt/Helix/ substitutes on current line only."""
        text = "4 Lightning Bolt\n2 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_substitute(
            buffer, cursor, _make_cmd(args="/Bolt/Helix/"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines[0] == "4 Lightning Helix"
        # Second line unchanged
        assert lines[1] == "2 Lightning Bolt"
        assert ctx.modified is True

    def test_sub_only_first_occurrence_without_g(self) -> None:
        """:s/a/b/ replaces only first occurrence on the line."""
        text = "4 Abrade and Abrade\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_substitute(
            buffer, cursor, _make_cmd(args="/Abrade/Helix/"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines[0] == "4 Helix and Abrade"


class TestSubWholeFile:
    def test_sub_whole_file(self) -> None:
        """:%s/Bolt/Helix/g substitutes across all lines."""
        text = "4 Lightning Bolt\n2 Lightning Bolt\n1 Shock\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = _make_cmd(
            args="/Bolt/Helix/g",
            cmd_range=CommandRange(start=0, end=2, is_whole_file=True),
        )

        new_buf, _ = cmd_substitute(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        assert lines[0] == "4 Lightning Helix"
        assert lines[1] == "2 Lightning Helix"
        assert lines[2] == "1 Shock"
        assert "2 substitutions" in ctx.message


class TestSubRange:
    def test_sub_range(self) -> None:
        """:5,10s/a/b/g only affects lines in range."""
        text = "1 Alpha\n2 Beta\n3 Alpha\n4 Delta\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        # Range covers lines 1-2 (0-indexed)
        cmd = _make_cmd(
            args="/Alpha/Gamma/g",
            cmd_range=CommandRange(start=2, end=2),
        )

        new_buf, _ = cmd_substitute(buffer, cursor, cmd, ctx)
        lines = _line_texts(new_buf)
        # Line 0 is outside range — unchanged
        assert lines[0] == "1 Alpha"
        # Line 2 is in range — changed
        assert lines[2] == "3 Gamma"
        assert "1 substitution" in ctx.message


class TestSubGlobalFlag:
    def test_sub_global_flag_replaces_all(self) -> None:
        """g flag replaces all occurrences on each line."""
        text = "4 Bolt Bolt Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_substitute(
            buffer, cursor, _make_cmd(args="/Bolt/Helix/g"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines[0] == "4 Helix Helix Helix"
        assert "3 substitutions" in ctx.message


class TestSubCaseInsensitive:
    def test_sub_case_insensitive(self) -> None:
        """i flag enables case-insensitive matching."""
        text = "4 lightning bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_substitute(
            buffer, cursor, _make_cmd(args="/Lightning/Helix/i"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines[0] == "4 Helix bolt"


class TestSubNoMatch:
    def test_sub_no_match(self) -> None:
        """No match produces informational message."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_substitute(
            buffer, cursor, _make_cmd(args="/Nonexistent/Helix/"), ctx
        )
        assert "Pattern not found" in ctx.message
        assert ctx.modified is False


class TestSubCountMessage:
    def test_sub_count_message_plural(self) -> None:
        """Count message uses correct plural form."""
        text = "4 Bolt Bolt Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        cmd_substitute(
            buffer, cursor, _make_cmd(args="/Bolt/X/g"), ctx
        )
        assert "3 substitutions" in ctx.message

    def test_sub_count_message_singular(self) -> None:
        """Count message uses singular when count is 1."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        cmd_substitute(
            buffer, cursor, _make_cmd(args="/Bolt/Helix/"), ctx
        )
        assert "1 substitution" in ctx.message
        assert "substitutions" not in ctx.message


class TestSubCardName:
    def test_sub_card_name(self) -> None:
        """Swap card names via substitute."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_substitute(
            buffer, cursor, _make_cmd(args="/Lightning Bolt/Lightning Helix/"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines[0] == "4 Lightning Helix"


class TestSubQuantity:
    def test_sub_quantity(self) -> None:
        """Change quantity numbers via substitute."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_substitute(
            buffer, cursor, _make_cmd(args="/4/3/"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines[0] == "3 Lightning Bolt"


class TestSubErrors:
    def test_sub_empty_args(self) -> None:
        """Empty args produces error."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        cmd_substitute(buffer, cursor, _make_cmd(args=""), ctx)
        assert "E: Usage" in ctx.message
        assert ctx.error is True

    def test_sub_insufficient_parts(self) -> None:
        """Too few parts produces error."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        cmd_substitute(buffer, cursor, _make_cmd(args="/only"), ctx)
        assert "E: " in ctx.message


class TestFilterView:
    def test_filter_placeholder(self) -> None:
        """:filter is a placeholder that returns informational message."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()
        cmd = ParsedCommand(name="filter", args="red")

        new_buf, _ = cmd_filter_view(buffer, cursor, cmd, ctx)
        assert "Filter: red" in ctx.message
        assert "not yet implemented" in ctx.message

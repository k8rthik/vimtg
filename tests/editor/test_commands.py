"""Tests for ex command parser and registry."""

from __future__ import annotations

import pytest

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRange,
    CommandRegistry,
    EditorContext,
    ParsedCommand,
    RangeError,
    parse_command,
)
from vimtg.editor.cursor import Cursor

# --- CommandRange.parse ---


class TestCommandRangeParse:
    def test_empty_string_returns_no_range(self) -> None:
        result = CommandRange.parse("", cursor_row=3, line_count=20)
        assert result.start is None
        assert result.end is None
        assert result.is_whole_file is False

    def test_percent_returns_whole_file(self) -> None:
        result = CommandRange.parse("%", cursor_row=0, line_count=10)
        assert result == CommandRange(start=0, end=9, is_whole_file=True)

    def test_dot_returns_current_line(self) -> None:
        result = CommandRange.parse(".", cursor_row=5, line_count=20)
        assert result == CommandRange(start=5, end=5)

    def test_dollar_returns_last_line(self) -> None:
        result = CommandRange.parse("$", cursor_row=0, line_count=20)
        assert result == CommandRange(start=19, end=19)

    def test_single_number(self) -> None:
        result = CommandRange.parse("7", cursor_row=0, line_count=20)
        assert result == CommandRange(start=6, end=6)

    def test_number_range(self) -> None:
        result = CommandRange.parse("5,10", cursor_row=0, line_count=20)
        assert result == CommandRange(start=4, end=9)

    def test_reversed_range_normalizes(self) -> None:
        result = CommandRange.parse("10,5", cursor_row=0, line_count=20)
        assert result == CommandRange(start=4, end=9)


# --- parse_command ---


class TestParseCommand:
    def test_parse_simple_write(self) -> None:
        result = parse_command(":w", cursor_row=0, line_count=10)
        assert result.name == "w"
        assert result.args == ""
        assert result.cmd_range is None
        assert result.bang is False

    def test_parse_with_args(self) -> None:
        result = parse_command(":sort cmc", cursor_row=0, line_count=10)
        assert result.name == "sort"
        assert result.args == "cmc"

    def test_parse_range(self) -> None:
        result = parse_command(":5,10sort", cursor_row=0, line_count=20)
        assert result.name == "sort"
        assert result.cmd_range is not None
        assert result.cmd_range.start == 4
        assert result.cmd_range.end == 9

    def test_parse_whole_file(self) -> None:
        result = parse_command(":%sort", cursor_row=0, line_count=20)
        assert result.cmd_range is not None
        assert result.cmd_range.is_whole_file is True
        assert result.cmd_range.start == 0
        assert result.cmd_range.end == 19

    def test_parse_bang(self) -> None:
        result = parse_command(":q!", cursor_row=0, line_count=10)
        assert result.name == "q"
        assert result.bang is True

    def test_parse_current_line(self) -> None:
        result = parse_command(":.", cursor_row=7, line_count=20)
        assert result.cmd_range is not None
        assert result.cmd_range.start == 7
        assert result.cmd_range.end == 7

    def test_parse_dollar(self) -> None:
        result = parse_command(":$", cursor_row=0, line_count=20)
        assert result.cmd_range is not None
        assert result.cmd_range.start == 19
        assert result.cmd_range.end == 19

    def test_parse_sort_bang_with_field(self) -> None:
        result = parse_command(":sort! qty", cursor_row=0, line_count=10)
        assert result.name == "sort"
        assert result.bang is True
        assert result.args == "qty"

    def test_parse_write_quit(self) -> None:
        result = parse_command(":wq", cursor_row=0, line_count=10)
        assert result.name == "wq"

    def test_parse_range_with_args(self) -> None:
        result = parse_command(":5,10sort cmc", cursor_row=0, line_count=20)
        assert result.name == "sort"
        assert result.args == "cmc"
        assert result.cmd_range is not None
        assert result.cmd_range.start == 4


# --- CommandRegistry ---


class TestCommandRegistry:
    @pytest.fixture()
    def registry(self) -> CommandRegistry:
        return CommandRegistry()

    @pytest.fixture()
    def sample_buffer(self) -> Buffer:
        return Buffer.from_text("4 Lightning Bolt\n2 Counterspell\n")

    def test_registry_execute(
        self, registry: CommandRegistry, sample_buffer: Buffer
    ) -> None:
        called_with: list[str] = []

        def handler(
            buf: Buffer, cur: Cursor, cmd: ParsedCommand, ctx: EditorContext
        ) -> tuple[Buffer, Cursor]:
            called_with.append(cmd.name)
            return buf, cur

        registry.register("test", handler)
        cmd = ParsedCommand(name="test")
        ctx = EditorContext()
        registry.execute(cmd, sample_buffer, Cursor(), ctx)
        assert called_with == ["test"]

    def test_registry_alias(
        self, registry: CommandRegistry, sample_buffer: Buffer
    ) -> None:
        calls: list[str] = []

        def handler(
            buf: Buffer, cur: Cursor, cmd: ParsedCommand, ctx: EditorContext
        ) -> tuple[Buffer, Cursor]:
            calls.append("called")
            return buf, cur

        registry.register("write", handler, aliases=["w"])
        cmd = ParsedCommand(name="w")
        ctx = EditorContext()
        registry.execute(cmd, sample_buffer, Cursor(), ctx)
        assert calls == ["called"]

    def test_registry_completions(self, registry: CommandRegistry) -> None:
        def noop(
            buf: Buffer, cur: Cursor, cmd: ParsedCommand, ctx: EditorContext
        ) -> tuple[Buffer, Cursor]:
            return buf, cur

        registry.register("sort", noop)
        registry.register("stats", noop)
        registry.register("set", noop)
        assert registry.get_completions("so") == ["sort"]
        assert registry.get_completions("s") == ["set", "sort", "stats"]

    def test_unknown_command(
        self, registry: CommandRegistry, sample_buffer: Buffer
    ) -> None:
        cmd = ParsedCommand(name="nonexistent")
        ctx = EditorContext()
        buf, cur = registry.execute(cmd, sample_buffer, Cursor(), ctx)
        assert ctx.message == "E492: Not an editor command: nonexistent"
        assert ctx.error is True

    def test_completions_include_aliases(
        self, registry: CommandRegistry
    ) -> None:
        def noop(
            buf: Buffer, cur: Cursor, cmd: ParsedCommand, ctx: EditorContext
        ) -> tuple[Buffer, Cursor]:
            return buf, cur

        registry.register("write", noop, aliases=["w"])
        completions = registry.get_completions("w")
        assert "w" in completions
        assert "write" in completions


class TestMarkAndOutOfRangeAddresses:
    def test_mark_addresses(self) -> None:
        marks = {"a": 2, "b": 5}
        cmd = parse_command("'a,'bd", cursor_row=0, line_count=10, marks=marks)
        assert cmd.name == "d"
        assert cmd.cmd_range == CommandRange(start=2, end=5)

    def test_visual_marks(self) -> None:
        cmd = parse_command("'<,'>sort!", 0, 10, marks={"<": 7, ">": 3})
        assert cmd.name == "sort" and cmd.bang
        assert cmd.cmd_range == CommandRange(start=3, end=7)

    def test_mixed_mark_and_number(self) -> None:
        cmd = parse_command("'a,$d", 0, 10, marks={"a": 4})
        assert cmd.cmd_range == CommandRange(start=4, end=9)

    def test_unset_mark_raises(self) -> None:
        with pytest.raises(RangeError, match="E20"):
            parse_command("'q,'rd", 0, 10, marks={})

    def test_mark_past_the_end_clamps(self) -> None:
        cmd = parse_command("'a", 0, 5, marks={"a": 40})
        assert cmd.cmd_range == CommandRange(start=4, end=4)

    def test_line_past_the_end_is_flagged(self) -> None:
        cmd = parse_command("999d", 0, 10)
        assert cmd.cmd_range is not None and cmd.cmd_range.out_of_range
        cmd = parse_command("1,999d", 0, 10)
        assert cmd.cmd_range is not None and cmd.cmd_range.out_of_range
        cmd = parse_command("10d", 0, 10)
        assert cmd.cmd_range is not None and not cmd.cmd_range.out_of_range

    def test_registry_refuses_out_of_range_with_e16(self) -> None:
        calls: list[ParsedCommand] = []

        def handler(
            buf: Buffer, cur: Cursor, cmd: ParsedCommand, ctx: EditorContext
        ) -> tuple[Buffer, Cursor]:
            calls.append(cmd)
            return buf, cur

        registry = CommandRegistry()
        registry.register("d", handler)
        buf = Buffer.from_text("a\nb\n")
        ctx = EditorContext()
        registry.execute(parse_command("999d", 0, buf.line_count()), buf, Cursor(), ctx)
        assert ctx.error and "E16: Invalid range" in ctx.message
        assert calls == []
        # A bare out-of-range number is a goto, which clamps (vim :999)
        ctx = EditorContext()
        _, cur = registry.execute(parse_command("999", 0, buf.line_count()), buf, Cursor(), ctx)
        assert not ctx.error and cur.row == buf.line_count() - 1


class TestFailPrefix:
    """A vim-coded error keeps its own code: 'E37: ...', never 'E: E37: ...'."""

    def test_vim_code_is_not_prefixed_again(self) -> None:
        ctx = EditorContext()
        ctx.fail("E37: No write since last change (add ! to override)")
        assert ctx.message == "E37: No write since last change (add ! to override)"
        assert ctx.error

    def test_plain_message_gets_the_generic_prefix(self) -> None:
        ctx = EditorContext()
        ctx.fail("Write failed: disk full")
        assert ctx.message == "E: Write failed: disk full"

    def test_generic_prefix_is_kept_once(self) -> None:
        ctx = EditorContext()
        ctx.fail("E: Unknown format")
        assert ctx.message == "E: Unknown format"

    def test_registry_range_error_reads_as_vim(self) -> None:
        registry = CommandRegistry()
        ctx = EditorContext()
        cmd = parse_command(":999d", 0, 3)
        registry.execute(cmd, Buffer.from_text("a\nb\nc\n"), Cursor(), ctx)
        assert ctx.message == "E16: Invalid range"

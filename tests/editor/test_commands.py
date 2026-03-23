"""Tests for ex command parser and registry."""

from __future__ import annotations

import pytest

from vimtg.editor.buffer import Buffer
from vimtg.editor.commands import (
    CommandRange,
    CommandRegistry,
    EditorContext,
    ParsedCommand,
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
        assert "Unknown command" in ctx.message
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

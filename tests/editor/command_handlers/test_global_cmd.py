"""Tests for the :g and :v global command handlers."""

from __future__ import annotations

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.global_cmd import cmd_global
from vimtg.editor.commands import EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _make_cmd(
    name: str = "g",
    args: str = "",
) -> ParsedCommand:
    return ParsedCommand(name=name, args=args)


def _line_texts(buffer: Buffer) -> list[str]:
    return [bl.text for bl in buffer.get_lines()]


class TestGlobalDelete:
    def test_global_delete(self) -> None:
        """:g/Bolt/d removes matching card lines."""
        text = "4 Lightning Bolt\n2 Counterspell\n1 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, new_cur = cmd_global(
            buffer, cursor, _make_cmd(args="/Bolt/d"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines == ["2 Counterspell"]
        assert "2 lines deleted" in ctx.message
        assert ctx.modified is True

    def test_global_multiple_matches(self) -> None:
        """All matching lines are deleted, not just the first."""
        text = (
            "4 Lightning Bolt\n"
            "2 Counterspell\n"
            "3 Shock\n"
            "1 Lightning Helix\n"
        )
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Lightning/d"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines == ["2 Counterspell", "3 Shock"]
        assert "2 lines deleted" in ctx.message

    def test_global_single_match(self) -> None:
        """Deleting a single matching line works."""
        text = "4 Lightning Bolt\n2 Counterspell\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Counterspell/d"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines == ["4 Lightning Bolt"]
        assert "1 lines deleted" in ctx.message


class TestGlobalInverse:
    def test_global_inverse_delete(self) -> None:
        """:v/SB:/d removes card lines NOT matching SB: prefix."""
        text = "4 Lightning Bolt\nSB: 2 Negate\n3 Shock\nSB: 1 Dispel\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(name="v", args="/SB:/d"), ctx
        )
        lines = _line_texts(new_buf)
        assert lines == ["SB: 2 Negate", "SB: 1 Dispel"]
        assert "2 lines deleted" in ctx.message


class TestGlobalNoMatch:
    def test_global_no_match(self) -> None:
        """No matches produces informational message."""
        text = "4 Lightning Bolt\n2 Counterspell\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Nonexistent/d"), ctx
        )
        assert "Pattern not found" in ctx.message
        # Buffer unchanged
        assert _line_texts(new_buf) == ["4 Lightning Bolt", "2 Counterspell"]


class TestGlobalInvalidPattern:
    def test_global_invalid_regex(self) -> None:
        """Invalid regex produces error message."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/[invalid/d"), ctx
        )
        assert "E: Invalid pattern" in ctx.message
        assert ctx.error is True


class TestGlobalMissingCommand:
    def test_global_missing_subcommand(self) -> None:
        """Missing sub-command after pattern produces error."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Bolt/"), ctx
        )
        assert "E: Usage" in ctx.message
        assert ctx.error is True

    def test_global_too_short_args(self) -> None:
        """Args too short to parse produces error."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args=""), ctx
        )
        assert "E: Usage" in ctx.message


class TestGlobalPreservesComments:
    def test_global_preserves_comments(self) -> None:
        """Only card lines are matched; comments are preserved."""
        text = (
            "// Creature\n"
            "4 Lightning Bolt\n"
            "2 Counterspell\n"
            "// Bolt is great\n"
        )
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Bolt/d"), ctx
        )
        lines = _line_texts(new_buf)
        # Comment lines with "Bolt" are NOT deleted
        assert "// Creature" in lines
        assert "// Bolt is great" in lines
        assert "2 Counterspell" in lines
        assert "1 lines deleted" in ctx.message

    def test_global_unsupported_subcommand(self) -> None:
        """Unsupported sub-command produces error."""
        text = "4 Lightning Bolt\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=0)
        ctx = EditorContext()

        new_buf, _ = cmd_global(
            buffer, cursor, _make_cmd(args="/Bolt/m0"), ctx
        )
        assert "E: Unsupported sub-command" in ctx.message
        assert ctx.error is True


class TestGlobalCursorAdjustment:
    def test_cursor_adjusts_after_delete(self) -> None:
        """Cursor row is clamped to valid range after lines are deleted."""
        text = "4 Lightning Bolt\n2 Counterspell\n3 Shock\n"
        buffer = Buffer.from_text(text)
        cursor = Cursor(row=2)  # On last line
        ctx = EditorContext()

        # Delete last two lines (Counterspell, Shock)
        new_buf, new_cur = cmd_global(
            buffer, cursor, _make_cmd(args="/spell|Shock/d"), ctx
        )
        assert new_cur.row <= new_buf.line_count() - 1
        assert new_cur.row >= 0


ZONED = (
    "// Deck: Zones\n"
    "1 Sol Ring\n"
    "SB: 2 Duress\n"
    "MB: 1 Sol Talisman\n"
    "CMD: 1 Atraxa, Praetors' Voice\n"
    "CMP: 1 Lurrus of the Dream-Den\n"
    "SB:\n"
    "  1 Solemn Simulacrum\n"
    "VS: Tron\n"
    "  -1 Sol Ring\n"
)


class TestGlobalAllZones:
    def test_global_sees_every_zone(self) -> None:
        buffer = Buffer.from_text(ZONED)
        ctx = EditorContext()
        new_buf, _ = cmd_global(buffer, Cursor(row=0), _make_cmd(args="/sol/d"), ctx)
        lines = _line_texts(new_buf)
        assert "1 Sol Ring" not in lines
        assert "MB: 1 Sol Talisman" not in lines
        assert "  1 Solemn Simulacrum" not in lines
        assert "3 lines deleted" in ctx.message
        # the plan entry and the empty block header survive
        assert "  -1 Sol Ring" in lines
        assert "SB:" in lines

    def test_global_matches_commander_and_companion(self) -> None:
        buffer = Buffer.from_text(ZONED)
        ctx = EditorContext()
        new_buf, _ = cmd_global(
            buffer, Cursor(row=0), _make_cmd(args="/^CM[DP]:/d"), ctx,
        )
        lines = _line_texts(new_buf)
        assert not any(line.startswith(("CMD:", "CMP:")) for line in lines)
        assert "2 lines deleted" in ctx.message

    def test_inverse_keeps_non_card_lines(self) -> None:
        buffer = Buffer.from_text(ZONED)
        ctx = EditorContext()
        new_buf, _ = cmd_global(
            buffer, Cursor(row=0), _make_cmd(name="v", args="/Atraxa/d"), ctx,
        )
        lines = _line_texts(new_buf)
        assert lines == [
            "// Deck: Zones",
            "CMD: 1 Atraxa, Praetors' Voice",
            "SB:",
            "VS: Tron",
            "  -1 Sol Ring",
        ]

    def test_block_card_deletion_keeps_zone_context(self) -> None:
        text = "SB:\n  1 Duress\n  2 Negate\n"
        buffer = Buffer.from_text(text)
        ctx = EditorContext()
        new_buf, _ = cmd_global(buffer, Cursor(row=0), _make_cmd(args="/Duress/d"), ctx)
        assert _line_texts(new_buf) == ["SB:", "  2 Negate"]
        assert new_buf.get_line(1).line_type.value == "sideboard"


class TestGlobalRange:
    """:[range]g — the range used to be parsed and ignored, so
    :1,2g/Bolt/d deleted every Bolt in the buffer."""

    def _run(self, cmd_range):  # type: ignore[no-untyped-def]
        from vimtg.editor.command_handlers.global_cmd import cmd_global
        from vimtg.editor.commands import CommandRange, EditorContext

        buf = Buffer.from_text("4 Bolt\n4 Opt\n4 Bolt\n4 Opt\n4 Bolt\n")
        cmd = ParsedCommand(
            name="g", args="/Bolt/d",
            cmd_range=CommandRange(**cmd_range) if cmd_range is not None else None,
        )
        ctx = EditorContext()
        new_buf, _ = cmd_global(buf, Cursor(), cmd, ctx)
        return _line_texts(new_buf), ctx.message

    def test_range_limits_the_lines_considered(self) -> None:
        lines, message = self._run({"start": 0, "end": 1})
        assert lines == ["4 Opt", "4 Bolt", "4 Opt", "4 Bolt"]
        assert message == "1 lines deleted"

    def test_no_range_and_percent_cover_the_whole_buffer(self) -> None:
        assert self._run(None)[0] == ["4 Opt", "4 Opt"]
        assert self._run({"start": 0, "end": 4, "is_whole_file": True})[0] == ["4 Opt", "4 Opt"]

    def test_a_range_past_the_end_is_clamped(self) -> None:
        assert self._run({"start": 3, "end": 40})[0] == ["4 Bolt", "4 Opt", "4 Bolt", "4 Opt"]


class TestInverseGlobalRange:
    """:v and :g! honour a typed range the same way :g does."""

    TEXT = "4 Lightning Bolt\n2 Counterspell\n1 Lightning Bolt\n3 Lightning Bolt\n"

    def _run(self, command: str) -> list[str]:
        from vimtg.editor.commands import parse_command

        buffer = Buffer.from_text(self.TEXT)
        cmd = parse_command(command, 0, buffer.line_count())
        new_buf, _ = cmd_global(buffer, Cursor(row=0), cmd, EditorContext())
        return _line_texts(new_buf)

    def test_v_acts_only_inside_its_range(self) -> None:
        assert self._run(":1,2v/Counter/d") == [
            "2 Counterspell", "1 Lightning Bolt", "3 Lightning Bolt",
        ]

    def test_g_bang_acts_only_inside_its_range(self) -> None:
        assert self._run(":3,4g!/Counter/d") == ["4 Lightning Bolt", "2 Counterspell"]

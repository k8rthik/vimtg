"""Tests for the deck tag commands :dtag and :duntag."""

from vimtg.editor.buffer import Buffer
from vimtg.editor.command_handlers.tag_cmds import (
    cmd_dtag,
    cmd_duntag,
)
from vimtg.editor.commands import CommandRange, EditorContext, ParsedCommand
from vimtg.editor.cursor import Cursor


def _buf(text: str) -> Buffer:
    return Buffer.from_text(text)


def _ctx() -> EditorContext:
    return EditorContext()


def _cmd(
    name: str, args: str = "", bang: bool = False, cmd_range: CommandRange | None = None,
) -> ParsedCommand:
    return ParsedCommand(name=name, args=args, bang=bang, cmd_range=cmd_range)


class TestCmdDtag:
    def test_add_deck_tag(self):
        buf = _buf("// Deck: Test\n\n4 Goblin Guide\n")
        ctx = _ctx()
        buf, _ = cmd_dtag(buf, Cursor(0, 0), _cmd("dtag", "aggro"), ctx)
        # Should have a // Tags: aggro line
        found = False
        for i in range(buf.line_count()):
            if "// Tags:" in buf.get_line(i).text:
                assert "aggro" in buf.get_line(i).text
                found = True
        assert found

    def test_add_to_existing_deck_tags(self):
        buf = _buf("// Deck: Test\n// Tags: aggro\n\n4 Goblin Guide\n")
        ctx = _ctx()
        buf, _ = cmd_dtag(buf, Cursor(0, 0), _cmd("dtag", "budget"), ctx)
        for i in range(buf.line_count()):
            text = buf.get_line(i).text
            if "// Tags:" in text:
                assert "aggro" in text
                assert "budget" in text


class TestCmdDuntag:
    def test_remove_deck_tag(self):
        buf = _buf("// Deck: Test\n// Tags: aggro, budget\n\n4 Goblin Guide\n")
        ctx = _ctx()
        buf, _ = cmd_duntag(buf, Cursor(0, 0), _cmd("duntag", "aggro"), ctx)
        for i in range(buf.line_count()):
            text = buf.get_line(i).text
            if "// Tags:" in text:
                assert "aggro" not in text
                assert "budget" in text

    def test_remove_last_deck_tag_leaves_empty_scaffold_line(self):
        buf = _buf("// Deck: Test\n// Tags: aggro\n\n4 Goblin Guide\n")
        ctx = _ctx()
        initial_count = buf.line_count()
        buf, _ = cmd_duntag(buf, Cursor(0, 0), _cmd("duntag", "aggro"), ctx)
        assert buf.line_count() == initial_count
        assert buf.get_line(1).text == "// Tags:"

    def test_removing_an_absent_tag_is_not_a_change(self):
        for text in (
            "// Deck: Test\n// Tags:\n\n4 Goblin Guide\n",
            "// Deck: Test\n// Tags: budget\n\n4 Goblin Guide\n",
        ):
            before = _buf(text)
            ctx = _ctx()
            after, _ = cmd_duntag(before, Cursor(0, 0), _cmd("duntag", "aggro"), ctx)
            assert after is before
            assert ctx.modified is False
            assert "No such deck tag: #aggro" in ctx.message
